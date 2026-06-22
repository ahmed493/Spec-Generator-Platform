from app.api import routes
from app.agents.mapping_agent import MappingAgent

print('pipeline_state keys:', list(routes._pipeline_state.keys())[:5])
if routes._pipeline_state:
    pid = list(routes._pipeline_state.keys())[0]
    st = routes._pipeline_state[pid]
    print('project id:', pid)
    print('template_text length:', len(st.get('template_text','')))
    print('placeholders:', len(st.get('placeholders', [])))
    print('values keys sample:', list(st.get('values', {}).keys())[:10])
    agent = MappingAgent()
    try:
        spec = agent.compose(st.get('template_text',''), st.get('values', {}), st.get('placeholders', []))
        print('COMPOSED length:', len(spec))
        print(spec[:1000])
    except Exception as e:
        import traceback
        traceback.print_exc()
        print('Mapping failed:', e)
else:
    print('no pipeline_state loaded')
