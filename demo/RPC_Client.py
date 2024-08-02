import liblgraph_client_python

client = liblgraph_client_python.client("127.0.0.1:9091", "admin", "73@TuGraph")


# ret, res = client.call_cypher("CALL db.edgeLabels()", "default", 10)
ret, res = client.callCypher("MATCH (n) RETUN n LIMIT 100", 'default')
print(ret,res)