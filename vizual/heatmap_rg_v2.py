import streamlit as st
import networkx as nx
import os

# Настройка страницы
st.set_page_config(page_title="Register Heatmap Log", layout="wide")
st.title("Лог ошибок регистров (Heatmap)", text_alignment="center")

# 1. Чтение данных из текстового файла
file_path = "log.txt"

# Инициализация массивов
addresses = []
writes_data = []
reads_data = []
errors_data = [] # Список списков [ro, mism, sticky, dead, ovf, unexp]

# Названия колонок ошибок (соответствуют столбцам в txt после Reads)
error_names = ["RO Denied", "Mismatch", "Sticky", "Deadlock", "Overflow", "Unexp"]
summary_lines = []

try:
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    is_parsing_table = False
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Сбор сводной статистики (все, что до таблицы)
        if "Адрес" in line and "|" in line:
            is_parsing_table = True
            continue
        if "-----" in line:
            continue
            
        if not is_parsing_table:
            summary_lines.append(line)
        else:
            # Парсинг строк таблицы: 0x00 | 207 | ...
            if line.startswith("0x"):
                parts = [p.strip() for p in line.split('|')]
                # parts[0] = Address
                # parts[1] = Writes
                # parts[2] = Reads
                # parts[3] = RO Denied
                # parts[4] = Mismatch
                # parts[5] = Sticky
                # parts[6] = Deadlock
                # parts[7] = Overflow
                # parts[8] = Unexp
                
                if len(parts) >= 9:
                    addresses.append(parts[0])
                    writes_data.append(parts[1])
                    reads_data.append(parts[2])
                    
                    # Собираем ошибки в список чисел
                    # Порядок: RO, Mism, Sticky, Dead, Ovf, Unexp
                    row_bugs = [int(parts[i]) for i in range(3, 9)]
                    errors_data.append(row_bugs)

except FileNotFoundError:
    st.error(f"Файл {file_path} не найден! Пожалуйста, создайте файл с логом.")
    st.stop()
except Exception as e:
    st.error(f"Ошибка при чтении файла: {e}")
    st.stop()

# --- Отображение Сводной Статистики ---
if summary_lines:
    with st.expander("Сводная статистика (развернуть)", expanded=False):
        st.code("\n".join(summary_lines), language="text")

# 2. Подготовка данных для Heatmap
num_registers = len(addresses)
num_errors = len(error_names)

# Собираем все значения ошибок в один плоский список для поиска min/max
all_bugs_flat = [val for row in errors_data for val in row]

# Находим минимум и максимум (без учета нулей, чтобы не ломать градиент)
non_zero_bugs = [b for b in all_bugs_flat if b > 0]
global_min = min(non_zero_bugs) if non_zero_bugs else 0
global_max = max(non_zero_bugs) if non_zero_bugs else 1

# 3. Структура NetworkX
G = nx.grid_2d_graph(num_errors, num_registers)
for x in range(num_errors):
    for y in range(num_registers):
        G.nodes[(x, y)]['freq'] = errors_data[y][x]
        G.nodes[(x, y)]['bug_name'] = error_names[x]

# 4. ПАЛИТРЫ
# Зеленая (для RO Denied)
green_colors = [
    "#112a14", "#163619", "#1c431f", "#225025", "#285e2c",
    "#2e6c32", "#357b39", "#3d8a41", "#449948", "#4ca950",
    "#54b858", "#61c265", "#70cc73", "#80d582", "#90de91",
    "#a1e7a2", "#b2efb3", "#c4f6c4", "#d5fcd5", "#e1fde1", "#edffed"
]

# Красная (для остальных ошибок)
red_colors = [
    "#3a0000", "#4d0000", "#600000", "#730000", "#860000",
    "#990000", "#ac0000", "#bf0000", "#d20000", "#e60000",
    "#f90000", "#ff1a1a", "#ff3333", "#ff4d4d", "#ff6666",
    "#ff8080", "#ff9999", "#ffb3b3", "#ffcccc", "#ffe6e6", "#fff0f0"
]

# 5. CSS Стили
# Немного адаптируем grid-template-columns под новое количество столбцов (3 инфо + 6 ошибок)
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
        /* Address, Writes, Reads, затем 6 колонок ошибок */
        grid-template-columns: 60px 60px 60px repeat(6, 65px);
        gap: 8px; 
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
        word-wrap: break-word;
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
        width: 65px;  
        height: 48px; 
        margin: 0; 
    }
    .cell-wrapper:hover {
        z-index: 1000; 
    }
    
    .grid-cell {
        width: 100%;
        height: 100%;
        border-radius: 6px; 
        border: 1px solid #444;
        transition: transform 0.1s ease, box-shadow 0.1s ease;
        cursor: pointer;
    }
    .cell-wrapper:hover .grid-cell {
        transform: scale(1.15); 
        border: 2px solid #fff;
        box-shadow: 0px 4px 12px rgba(255, 255, 255, 0.3); 
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
    .custom-tooltip b { color: #ffab40; }
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
        margin-left: 10px; 
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
gradient_green_css = f"linear-gradient(to top, {', '.join(green_colors)})"
gradient_red_css = f"linear-gradient(to top, {', '.join(red_colors)})"

html_content = '<div class="main-layout">'

# --- ТАБЛИЦА ---
html_content += '<div class="heatmap-container">'
html_content += '<div></div>' # Пустой угол
html_content += '<div class="grid-header" style="color:#aaa; align-self:end;">Writes</div>'
html_content += '<div class="grid-header" style="color:#aaa; align-self:end;">Reads</div>'

# Заголовки ошибок
for name in error_names:
    # Делаем перенос строк для длинных названий, если нужно
    display_name = name.replace(" ", "<br>")
    html_content += f'<div class="grid-header" style="align-self:end;">{display_name}</div>'

# Тело таблицы
for y in range(num_registers):
    html_content += f'<div class="grid-text-cell grid-address">{addresses[y]}</div>'
    html_content += f'<div class="grid-text-cell">{writes_data[y]}</div>'
    html_content += f'<div class="grid-text-cell">{reads_data[y]}</div>'
    
    for x in range(num_errors):
        node_data = G.nodes[(x, y)]
        freq = node_data['freq']
        bug_name = node_data['bug_name']
        
        fallback_title = f"{bug_name}: {freq if freq > 0 else 'Ok'}"
        html_content += f'<div class="cell-wrapper" title="{fallback_title}">'
        
        if freq == 0:
            html_content += '<div class="grid-cell grid-cell-empty"></div>'
            html_content += f'<span class="custom-tooltip"><b>{bug_name}</b><br>Ошибок нет</span>'
        else:
            # Расчет интенсивности
            ratio = (freq - global_min) / (global_max - global_min) if global_max > global_min else 1.0
            
            # ВЫБОР ЦВЕТА: RO Denied (индекс 0) - Зеленый, остальные - Красный
            if bug_name == "RO Denied":
                palette = green_colors
            else:
                palette = red_colors
                
            color_index = int(round(ratio * (len(palette) - 1)))
            hex_color = palette[color_index] 
            
            html_content += f'<div class="grid-cell" style="background-color: {hex_color};"></div>'
            html_content += f'<span class="custom-tooltip"><b>{bug_name}</b><br>Количество: {freq}</span>'
            
        html_content += '</div>'

html_content += '</div>'

# --- ЛЕГЕНДА ---
html_content += '<div class="legend-wrapper">'
# Зеленая шкала (RO Denied)
html_content += f'<div class="legend-color-bar" style="background: {gradient_green_css};" title="RO Denied Scale"></div>'
# Красная шкала (Errors)
html_content += f'<div class="legend-color-bar" style="background: {gradient_red_css}; margin-left: 8px;" title="Error Scale"></div>'

html_content += '<div class="legend-labels-container">'

# Собираем значения для шкалы: min, max и кратные 500 (или 50 для мелких чисел, если нужно)
# Здесь оставляем логику кратно 500 из предыдущего примера, но можно адаптировать
legend_values = set([global_min, global_max])
step = 50 if global_max < 500 else 500 # Адаптивный шаг

for v in range(0, global_max + 1, step):
    if v > global_min and v < global_max:
        legend_values.add(v)

legend_values = sorted(list(legend_values))

# Рисуем подписи 
for val in legend_values:
    if global_max > global_min:
        percent = (val - global_min) / (global_max - global_min) * 100
    else:
        percent = 100
        
    html_content += f'<div class="legend-label" style="bottom: {percent}%;"><span class="legend-arrow">◀</span> {val}</div>'

html_content += '</div></div>' # Закрытие legend
html_content += '</div>'       # Закрытие main-layout

# 7. Вывод на экран
st.markdown(css + html_content, unsafe_allow_html=True)