import streamlit as st
import networkx as nx
import matplotlib.pyplot as plt
import json
import os

st.set_page_config(page_title="Граф FSM", layout="centered")
st.title("FSM граф ", text_alignment="center")

# 1. Определяем путь к папке, в которой находится этот скрипт
script_dir = os.path.dirname(os.path.abspath(__file__))
# Формируем полный путь к файлу fsm.json
json_file_path = os.path.join(script_dir, "fsm.json")

# 2. Проверяем существование файла и читаем его
if not os.path.exists(json_file_path):
    st.error(f"Файл не найден: `{json_file_path}`.\n\nПожалуйста, создайте файл `fsm.json` в той же папке, где находится программа.")
    st.stop() # Останавливаем выполнение скрипта, чтобы не было ошибок

with open(json_file_path, "r", encoding="utf-8") as f:
    edges = json.load(f)

# 3. Задаем жесткий порядок узлов, чтобы по кругу они шли логично
ordered_nodes =[
    "RESET_IDLE", 
    "DLAB_ENABLED", 
    "BAUDRATE_SET", 
    "OPERATIONAL_READY", 
    "TX_WAITING", 
    "TX_TRANSMITTING", 
    "RO_PROTECTION_TRIGGERED"
]

G = nx.DiGraph()
G.add_nodes_from(ordered_nodes) # Сначала добавляем узлы в правильном порядке
G.add_edges_from(edges)         # Затем добавляем связи из JSON

pos = nx.circular_layout(G)

# Делаем холст чуть больше, чтобы все поместилось
fig, ax = plt.subplots(figsize=(12, 12))

# --- ИЗМЕНЕНИЕ 1 ---
# Формируем словарь лейблов, заменяя "_" на "\n". 
# Это сделает текстовые блоки похожими на квадраты, а не на длинные прямоугольники.
display_labels = {node: node.replace("_", "\n") for node in G.nodes()}

# --- ИЗМЕНЕНИЕ 2 ---
# Отрисовка стрелок с правильным просчетом границ
nx.draw_networkx_edges(
    G, pos,
    ax=ax,
    edge_color='#2c3e50',
    arrows=True,
    arrowsize=25,
    node_shape="s",  # Указываем, что узлы имеют прямоугольную/квадратную форму ('s' = square)
    node_size=8000,  # Размер подогнан под новые "квадратные" лейблы (вместо 12000)
    connectionstyle="arc3,rad=0.3" 
)

# 5. Отрисовка текста (самих узлов)
nx.draw_networkx_labels(
    G, pos,
    labels=display_labels, # Передаем наши многострочные лейблы
    ax=ax,
    font_size=11,
    font_weight="bold",
    bbox=dict(
        facecolor="lightcyan", 
        edgecolor="black", 
        boxstyle="round,pad=0.9" # Чуть увеличили pad (отступ), чтобы текст дышал
    )
)

# Расширяем границы, чтобы крайние блоки не обрезались
ax.margins(0.3)
plt.axis("off")

st.pyplot(fig)