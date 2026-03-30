"""
SSO Authentication for FastAPI (Azure AD & Google Cloud Identity)
- Supports both Azure AD (OIDC) and Google (OIDC)
- Provides user info and role extraction
- Use `get_current_user` for authentication
- Use `require_role` for RBAC
"""
from fastapi import FastAPI, Depends, HTTPException, status, Security
from fastapi.security import OAuth2AuthorizationCodeBearer
from jose import jwt, JWTError
import requests
import os
from app.db import SessionLocal
from app.models import User, Role, Base
from sqlalchemy.orm import Session

# --- Config ---
SSO_PROVIDER = os.getenv("SSO_PROVIDER", "azure")  # 'azure' or 'google'

# Azure AD
AZURE_TENANT_ID = os.getenv("AZURE_TENANT_ID", "<your-tenant-id>")
AZURE_CLIENT_ID = os.getenv("AZURE_CLIENT_ID", "<your-client-id>")
AZURE_CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET", "<your-client-secret>")
AZURE_AUTHORITY = f"https://login.microsoftonline.com/{AZURE_TENANT_ID}"
AZURE_OIDC_CONFIG = requests.get(f"{AZURE_AUTHORITY}/v2.0/.well-known/openid-configuration").json()
AZURE_JWKS_URI = AZURE_OIDC_CONFIG["jwks_uri"]
AZURE_ALGORITHMS = ["RS256"]

# Google
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "<your-google-client-id>")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "<your-google-client-secret>")
GOOGLE_OIDC_CONFIG = requests.get("https://accounts.google.com/.well-known/openid-configuration").json()
GOOGLE_JWKS_URI = GOOGLE_OIDC_CONFIG["jwks_uri"]
GOOGLE_ALGORITHMS = ["RS256"]

# --- OAuth2 Schemes ---
oauth2_schemes = {
    "azure": OAuth2AuthorizationCodeBearer(
        authorizationUrl=AZURE_OIDC_CONFIG["authorization_endpoint"],
        tokenUrl=AZURE_OIDC_CONFIG["token_endpoint"],
        scopes={"openid": "OpenID Connect"}
    ),
    "google": OAuth2AuthorizationCodeBearer(
        authorizationUrl=GOOGLE_OIDC_CONFIG["authorization_endpoint"],
        tokenUrl=GOOGLE_OIDC_CONFIG["token_endpoint"],
        scopes={"openid": "OpenID Connect"}
    )
}

def get_jwks(provider):
    if provider == "azure":
        return requests.get(AZURE_JWKS_URI).json()["keys"]
    else:
        return requests.get(GOOGLE_JWKS_URI).json()["keys"]

def decode_jwt(token: str, provider: str):
    try:
        unverified_header = jwt.get_unverified_header(token)
        keys = get_jwks(provider)
        for key in keys:
            if key["kid"] == unverified_header["kid"]:
                return jwt.decode(
                    token,
                    key,
                    algorithms=AZURE_ALGORITHMS if provider == "azure" else GOOGLE_ALGORITHMS,
                    audience=AZURE_CLIENT_ID if provider == "azure" else GOOGLE_CLIENT_ID,
                    issuer=(AZURE_OIDC_CONFIG["issuer"] if provider == "azure" else GOOGLE_OIDC_CONFIG["issuer"])
                )
        raise HTTPException(status_code=401, detail="Invalid token header")
    except JWTError as e:
        raise HTTPException(status_code=401, detail="Token decode error")

def get_current_user(token: str = Depends(lambda: oauth2_schemes[SSO_PROVIDER])):
    payload = decode_jwt(token, SSO_PROVIDER)
    roles = payload.get("roles", []) if SSO_PROVIDER == "azure" else payload.get("hd", [])
    db: Session = SessionLocal()
    user = db.query(User).filter_by(sub=payload["sub"]).first()
    if not user:
        user = User(
            sub=payload["sub"],
            email=payload.get("email"),
            name=payload.get("name"),
            provider=SSO_PROVIDER
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    # Sync roles
    if roles:
        user_roles = {r.name for r in user.roles}
        for role_name in roles:
            role = db.query(Role).filter_by(name=role_name).first()
            if not role:
                role = Role(name=role_name)
                db.add(role)
                db.commit()
                db.refresh(role)
            if role.name not in user_roles:
                user.roles.append(role)
        db.commit()
    db.close()
    return {
        "sub": user.sub,
        "email": user.email,
        "roles": [r.name for r in user.roles],
        "name": user.name,
        "provider": user.provider
    }

def require_role(role: str):
    def role_checker(user=Depends(get_current_user)):
        if role not in user["roles"]:
            raise HTTPException(status_code=403, detail="Insufficient role")
        return user
    return role_checker

# --- FastAPI Example ---
app = FastAPI()

@app.get("/protected")
def protected_route(user=Depends(get_current_user)):
    return {"user": user}

@app.get("/admin")
def admin_route(user=Depends(require_role("Admin"))):
    return {"admin": user}
