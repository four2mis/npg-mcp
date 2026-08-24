import ast

with open('npg_mcp/client.py') as f:
    ast.parse(f.read())
print('client.py syntax OK')

with open('tests/test_client.py') as f:
    ast.parse(f.read())
print('test_client.py syntax OK')
