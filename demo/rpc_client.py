import liblgraph_client_python

client = liblgraph_client_python.client("127.0.0.1:9090", "admin", "73@TuGraph")

ret, res = client.callCypher("MATCH (n) RETURN n LIMIT 1", 'MovieDemo1') # cypher, graph
if ret:
    print(res)
