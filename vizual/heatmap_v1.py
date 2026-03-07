import streamlit as st
import networkx as nx

# Настройка страницы
st.set_page_config(page_title="Discrete Spectrum Heatmap", layout="wide")
st.title("Лог ошибок: Плотный график с легендой")
st.write("Спектрограмма использует целые круглые числа с шагом 500. Расстояния между ячейками одинаковые со всех сторон.")

# 1. Исходные данные
log_data = """
------------------------------------------------------------------------------------------
Адрес    | Writes   | Reads    | Bug 1 (Stk)  | Bug 2 (Dead) | Bug 3 (Ovf)  | Unexp   
------------------------------------------------------------------------------------------
0x00     | 2121     | 2068     | 100          | 200          | 300          | 400       
0x04     | 2020     | 2063     | 500          | 600          | 700          | 800       
0x08     | 1964     | 2021     | 900          | 1000         | 1100         | 1200      
0x0C     | 1986     | 2028     | 1300         | 1400         | 1500         | 1600      
0x10     | 1898     | 2064     | 1700         | 1800         | 1900         | 2000      
0x14     | 2058     | 2015     | 2100         | 0            | 0            | 0         
0x18     | 2031     | 2118     | 0            | 0            | 0            | 0         
0x1C     | 2040     | 2020     | 150          | 450          | 1050         | 1950      
0x20     | 2095     | 2017     | 0            | 2100         | 100          | 0         
0x24     | 2035     | 2079     | 1100         | 0            | 0            | 2050      
0x28     | 2050     | 2031     | 0            | 0            | 0            | 0         
0x2C     | 2024     | 1993     | 250          | 750          | 1250         | 1750      
0x30     | 2023     | 2012     | 0            | 0            | 0            | 0         
0x34     | 1982     | 2048     | 800          | 1600         | 2100         | 100       
0x38     | 2020     | 2012     | 0            | 0            | 0            | 0         
0x3C     | 2038     | 2026     | 100          | 1000         | 1500         | 2100      
------------------------------------------------------------------------------------------
"""

# 2. Парсинг данных
addresses, writes_data, reads_data, errors_data = [], [], [], []
error_names = ["Bug 1 (Stk)", "Bug 2 (Dead)", "Bug 3 (Ovf)", "Unexp"]
all_bugs_flat = [] 

for line in log_data.strip().split('\n'):
    if line.startswith('-') or line.startswith('Адрес'):
        continue
    parts = [p.strip() for p in line.split('|')]
    if len(parts) == 7:
        addresses.append(parts[0])
        writes_data.append(parts[1])
        reads_data.append(parts[2])
        
        bugs = [int(parts[3]), int(parts[4]), int(parts[5]), int(parts[6])]
        errors_data.append(bugs)
        all_bugs_flat.extend(bugs)

num_registers = len(addresses)
num_errors = len(error_names)

# Находим минимум и максимум (без учета нулей)
non_zero_bugs = [b for b in all_bugs_flat if b > 0]
global_min = min(non_zero_bugs) if non_zero_bugs else 0
global_max = max(non_zero_bugs) if non_zero_bugs else 1

# 3. Структура NetworkX
G = nx.grid_2d_graph(num_errors, num_registers)
for x in range(num_errors):
    for y in range(num_registers):
        G.nodes[(x, y)]['freq'] = errors_data[y][x]
        G.nodes[(x, y)]['bug_name'] = error_names[x]

# 4. ДИСКРЕТНАЯ ПАЛИТРА (21 цвет)
discrete_colors = [
    "#3B0082", "#6A0DAD", "#8A2BE2", # Фиолетовые
    "#00008B", "#0000FF", "#3399FF", # Синие
    "#008B8B", "#00CED1", "#00FFFF", # Голубые
    "#005500", "#00A000", "#00FF00", # Зеленые 
    "#9ACD32", "#FFFF00", "#FFD700", # Желтые
    "#FFA500", "#FF8C00", "#FF4500", # Оранжевые
    "#FF3333", "#E60000", "#8B0000"  # Красные
]

# 5. CSS Стили
css = """
<style>
    .stApp { overflow: visible !important; }
    
    .main-layout {
        display: flex;
        flex-direction: row;
        justify-content: center;
        align-items: flex-start;
        gap: 50px;
        margin-top: 30px;
        padding-bottom: 80px;
    }

    .heatmap-container {
        display: grid;
        /* Колонки под размер: Адрес(50px), Writes(55px), Reads(55px) и 4 ошибки (по 48px) */
        grid-template-columns: 50px 55px 55px repeat(4, 48px);
        gap: 8px; /* Единый идеальный отступ в 8px между всеми колонками и строками */
        align-items: center;
        position: relative;
    }
    
    .grid-header {
        font-weight: bold;
        text-align: center;
        font-size: 13px; 
        color: #e0e0e0;
        padding-bottom: 5px;
        line-height: 1.2;
    }
    .grid-text-cell {
        font-family: monospace;
        font-size: 14px;
        text-align: center;
        color: #bbb;
    }
    .grid-address {
        text-align: right;
        padding-right: 10px;
        color: #fff;
    }
    
    .cell-wrapper {
        position: relative;
        width: 48px;  /* Ширина строго равна ширине колонки (gap делает отступы) */
        height: 48px; /* Квадрат */
        margin: 0; 
    }
    .cell-wrapper:hover {
        z-index: 1000; 
    }
    
    .grid-cell {
        width: 100%;
        height: 100%;
        border-radius: 8px; 
        border: 1px solid #555;
        transition: transform 0.1s ease, box-shadow 0.1s ease;
        cursor: pointer;
    }
    .cell-wrapper:hover .grid-cell {
        transform: scale(1.15); 
        border: 2px solid #fff;
        box-shadow: 0px 4px 12px rgba(255, 255, 255, 0.4);
    }
    .grid-cell-empty {
        background-color: transparent;
        border: 1px dashed #444;
    }

    .custom-tooltip {
        visibility: hidden;
        background-color: #1a1a1a;
        color: #ffffff;
        text-align: center;
        border-radius: 6px;
        padding: 8px 12px;
        position: absolute;
        bottom: 120%; 
        left: 50%;
        transform: translateX(-50%);
        opacity: 0;
        transition: opacity 0.15s, bottom 0.15s;
        font-size: 13px;
        font-family: sans-serif;
        white-space: nowrap;
        border: 1px solid #555;
        pointer-events: none; 
        box-shadow: 0px 10px 20px rgba(0,0,0,0.9);
        z-index: 99999 !important; 
    }
    .custom-tooltip b { color: #ffeb3b; }
    .custom-tooltip::after {
        content: "";
        position: absolute;
        top: 100%;
        left: 50%;
        margin-left: -6px;
        border-width: 6px;
        border-style: solid;
        border-color: #555 transparent transparent transparent;
    }
    .cell-wrapper:hover .custom-tooltip {
        visibility: visible;
        opacity: 1;
        bottom: 130%; 
    }

    .legend-wrapper {
        display: flex;
        flex-direction: row;
        /* Математический расчет: 16 ячеек по 48px + 15 отступов по 8px = 888px */
        height: 888px; 
        margin-top: 45px; 
    }
    .legend-color-bar {
        width: 35px; 
        height: 100%;
        border-radius: 6px;
        border: 1px solid #555;
    }
    .legend-labels-container {
        position: relative;
        height: 100%;
        width: 100px; 
        margin-left: 5px; 
    }
    .legend-label {
        position: absolute;
        left: 0;
        transform: translateY(50%);
        display: flex;
        align-items: center;
        gap: 6px; 
        font-size: 15px;
        color: #fff;
        font-family: monospace; 
        font-weight: bold;
    }
    .legend-arrow {
        color: #bbb;
        font-size: 16px;
    }
</style>
"""

# 6. ГЕНЕРАЦИЯ HTML
gradient_css = f"linear-gradient(to top, {', '.join(discrete_colors)})"

html_content = '<div class="main-layout">'

# --- ТАБЛИЦА ---
html_content += '<div class="heatmap-container">'
html_content += '<div></div>'
html_content += '<div class="grid-header" style="color:#aaa; align-self:end;">Writes</div>'
html_content += '<div class="grid-header" style="color:#aaa; align-self:end;">Reads</div>'

# Делаем перенос строк в шапках, чтобы они вмещались в ровные узкие столбцы
for name in error_names:
    display_name = name.replace(" (", "<br>(")
    html_content += f'<div class="grid-header" style="align-self:end;">{display_name}</div>'

for y in range(num_registers):
    html_content += f'<div class="grid-text-cell grid-address">{addresses[y]}</div>'
    html_content += f'<div class="grid-text-cell">{writes_data[y]}</div>'
    html_content += f'<div class="grid-text-cell">{reads_data[y]}</div>'
    
    for x in range(num_errors):
        node_data = G.nodes[(x, y)]
        freq = node_data['freq']
        bug_name = node_data['bug_name']
        
        fallback_title = f"{bug_name}: {freq if freq > 0 else 'Нет ошибок'}"
        html_content += f'<div class="cell-wrapper" title="{fallback_title}">'
        
        if freq == 0:
            html_content += '<div class="grid-cell grid-cell-empty"></div>'
            html_content += f'<span class="custom-tooltip"><b>{bug_name}</b><br>Ошибок нет</span>'
        else:
            ratio = (freq - global_min) / (global_max - global_min) if global_max > global_min else 1.0
            color_index = int(round(ratio * (len(discrete_colors) - 1)))
            hex_color = discrete_colors[color_index]
            
            html_content += f'<div class="grid-cell" style="background-color: {hex_color};"></div>'
            html_content += f'<span class="custom-tooltip"><b>{bug_name}</b><br>Количество: {freq}</span>'
            
        html_content += '</div>'

html_content += '</div>'

# --- ЛЕГЕНДА С КРАТНЫМИ 500 ЗНАЧЕНИЯМИ ---
html_content += '<div class="legend-wrapper">'
html_content += f'<div class="legend-color-bar" style="background: {gradient_css};"></div>'
html_content += '<div class="legend-labels-container">'

# Собираем значения: минимум, максимум и все числа кратные 500
legend_values = set([global_min, global_max])
for v in range(0, global_max + 1, 500):
    if v > global_min and v < global_max:
        legend_values.add(v)

legend_values = sorted(list(legend_values))

# Рисуем подписи (их высота вычисляется математически)
for val in legend_values:
    if global_max > global_min:
        percent = (val - global_min) / (global_max - global_min) * 100
    else:
        percent = 100
        
    html_content += f'<div class="legend-label" style="bottom: {percent}%;"><span class="legend-arrow">◀</span> {val}</div>'

html_content += '</div></div>' # Закрытие legend-labels-container и legend-wrapper
html_content += '</div>'       # Закрытие main-layout

# 7. Вывод на экран
st.markdown(css + html_content, unsafe_allow_html=True)