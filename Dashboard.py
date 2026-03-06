import matplotlib.pyplot as plt
import networkx as nx 

G = nx.DiGraph()

G.add_node('IDLE')
G.add_node('Read')
G.add_node('Write')
G.add_node('Deadlock')

G.add_edge('IDLE','Read')
G.add_edge('Read','Write')
G.add_edge('Write','Deadlock')
G.add_edge('IDLE','Read')