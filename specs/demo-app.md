# Expression de besoin — Dunning B2c Unpaid Internal Report Command

| Champ | Valeur |
|---|---|
| Projet | Dunning B2c Unpaid Internal Report Command |
| Rédaction | [À compléter] |
| Destinataire(s) | [À compléter] |
| Date de rédaction | [À compléter] |
| Validation / Date | [À compléter] |
| Code budgétaire | [À compléter] |
| Version | [À compléter] |
| Auteur | [À compléter] |
| Historique | [À compléter] |

## 1. Description du besoin

**Description du besoin** : The Dunning B2C Unpaid Internal Report Command generates an export of unpaid B2C invoices from Sage for internal purposes only, which is then sent via email. (in DunningB2cUnpaidInternalReportCommand.php: setDescription())

## 2. Traitement

**Obligations liées aux données personnelles et/ou sensibles** :
- Flux devant respecter la RGPD (OUI/NON)
- Source à crypter/décrypter
- Destination à crypter/décrypter

**Historisation des données** : [À compléter]

**Gestion des erreurs** : In DunningB2cUnpaidInternalReportCommand.php: Errors are handled using try-catch blocks, with error messages logged and email notifications sent on exceptions.

**Gestion des rejets** : [À compléter]

**Mise à disposition des données** : In DunningB2cUnpaidInternalReportCommand.php: The command checks for valid recipients for the report before sending it.

**Exploitation** : In DunningB2cUnpaidInternalReportCommand.php: Contact is implied through the error handling that sends mails to inform about issues.

**Observabilité** : [À compléter]

## 3. Interface(s) d'entrée

**Connectivité d’entrée** : Sage API via Service/Sage/Client.php and MySQL table stop_relance via EntityManager in DunningB2cUnpaidInternalReportCommand.php.

**Format de l’interface** : Input data includes fields detailing customer unpaid invoices such as 'customer_number', 'contract_number', 'contract_status' among others. In DunningB2cUnpaidInternalReportCommand.php: ...

**Application source** : Sage API via Ve/AccountingBundle/Service/Sage/Client.php

**Types de connexion** :
- API
- DB

**Protocole de transferts des données** : Data is transferred via HTTP calls to the Sage API and database queries to MySQL, specifically using SQL in the getB2CUnpaidInternalData method.

**Type/Mode d’authentification** : [À compléter]

**Type de cryptage** : [À compléter]

**Nombre de source en entrée** : 1

**Nombre de champ par source** : 10

**Volume de données par source** : <1000

**Fréquence de réception** : 1 fois par jour

**Fichier d’exemple** : [À compléter]

**Format de l’interface Source 1** : CSV via fputcsv in DunningB2cUnpaidInternalReportCommand.php

**Emplacement du fichier** : php://temp in DunningB2cUnpaidInternalReportCommand.php

**Nom du fichier source** : reporting_interne_impaye_b2c_<date>.csv in DunningB2cUnpaidInternalReportCommand.php

**Format du fichier** : Csv

**Spécificités du format de fichier CSV** : Header includes N° Client, N° Contrat, Type Énergie, Statut contrat, Montant impayé, Montant douteux, Date échéance minimum, Etat recouvrement, Agence en charge, Stop relance actif (oui/non) in DunningB2cUnpaidInternalReportCommand.php

**Existence de l’entête** : oui

**Encodage du fichier CSV** : UTF-8 BOM

**Séparateurs des champs** : ;

**Quote caractère** : [À compléter]

**Caractère d'échappement** : [À compléter]

**Valeur du champ nul** : [À compléter]

**Spécificités du format de fichier JSON** : [À compléter]

**Spécificités du format de fichier Parquet** : [À compléter]

**Encodage du fichier Parquet** : [À compléter]

**Compression du Parquet** : [À compléter]

**Contenu** : FULL

**Fréquence de réception du fichier** : 1 fois par mois

**Volume du fichier** : Centaines

## 4. Interface(s) de sortie

**Connectivité de sortie** : Email sent via Swift_Mailer with recipients specified as an option in DunningB2cUnpaidInternalReportCommand.php. Data is written to a CSV file that is then attached in the email.

**Format de l’interface** : CSV format, as indicated by the use of fputcsv in DunningB2cUnpaidInternalReportCommand.php.

**Application cible** : Swift_Mailer via sendByHtmlContent method (in DunningB2cUnpaidInternalReportCommand.php: ...)

**Types de connexion** : [À compléter]

**Protocole de transferts des données** : email via Swift_Mailer (in DunningB2cUnpaidInternalReportCommand.php: ...)

**Type/Mode d’authentification** : [À compléter]

**Type de cryptage** : [À compléter]

**Format du fichier** : Csv

**Emplacement du fichier** : php://temp (in DunningB2cUnpaidInternalReportCommand.php: ...)

**Nom du fichier cible** : reporting_interne_impaye_b2c_[date].csv (in DunningB2cUnpaidInternalReportCommand.php: ...)

**Spécificités du format de fichier CSV** : Le fichier CSV contient des données sur les paiements impayés avec des colonnes spécifiques comme N° Client, N° Contrat, Type Énergie, etc. (in DunningB2cUnpaidInternalReportCommand.php: ...)

**Existence de l’entête** : oui

**Encodage du fichier CSV** : UTF-8 BOM

**Séparateurs des champs** : ;

**Quote caractère** : [À compléter]

**Caractère d'échappement** : [À compléter]

**Valeur du champ nul** : [À compléter]

**Spécificités du format de fichier JSON** : [À compléter]

**Spécificités du format de fichier Parquet** : [À compléter]

**Encodage du fichier Parquet** : [À compléter]

**Compression du Parquet** : [À compléter]

**Contenu** : [À compléter]

**Fréquence de mise à jour de la base** : [À compléter]

**Volume de la base** : [À compléter]

## 5. Structure de l'interface

**Nom du champ** : stop_relance_actif

**Description** : Ce champ indique si un arrêt de relance est actif (oui/non) (in DunningB2cUnpaidInternalReportCommand.php: ...).

**Règle de transformation** : in_array($customer['contract_number'], $validStopRelance) ? 'Oui' : 'Non'

## 6. Mapping des champs

**Mapping  : Champ CSV , Colonne BD source, Règle de transformation , Table, BDD** :

| Champ CSV | Colonne BD source | Règle de transformation | Table | BDD |
|---|---|---|---|---|
| N° Client | customer_number | Direct mapping | V_SOLDES_RECOUVREMENT_B2C | SAGE |
| N° Contrat | contract_number | Direct mapping | V_SOLDES_RECOUVREMENT_B2C | SAGE |
| Type Énergie | type_energie | Direct mapping | V_SOLDES_RECOUVREMENT_B2C | SAGE |
| Statut contrat | contract_status | Direct mapping | V_SOLDES_RECOUVREMENT_B2C | SAGE |
| Montant impayé | montant_imp | round($customer['montant_imp'], 2) | V_SOLDES_RECOUVREMENT_B2C | SAGE |
| Montant douteux | montant_dtx | round($customer['montant_dtx'], 2) | V_SOLDES_RECOUVREMENT_B2C | SAGE |
| Date échéance minimum | minimum_due_date | Direct mapping | V_SOLDES_RECOUVREMENT_B2C | SAGE |
| Etat recouvrement | recovery_state | Direct mapping | V_SOLDES_RECOUVREMENT_B2C | SAGE |
| Agence en charge | recovery_agence | Direct mapping | V_SOLDES_RECOUVREMENT_B2C | SAGE |
| Stop relance actif (oui/non) | validStopRelance | in_array($customer['contract_number'], $validStopRelance) ? 'Oui' : 'Non' | V_SOLDES_RECOUVREMENT_B2C | SAGE |
