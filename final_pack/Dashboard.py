import streamlit as st
import networkx as nx
import os
import subprocess
import re
import sys

# --- 1. Настройка страницы ---
st.set_page_config(page_title="QA Dashboard", layout="wide")

# --- 2. Боковая панель для навигации ---
st.sidebar.title("Навигация")
app_mode = st.sidebar.radio("Выберите режим:", ["Heatmap Ошибок", "Оценка Pylint", "Покрытие"])

# --- Общие стили для кнопок (применяются ко всем вкладкам) ---
st.markdown("""
<style>
/* Увеличиваем основные кнопки запуска */
div.stButton > button {
    font-size: 24px !important;
    font-weight: bold !important;
    padding: 15px 30px !important;
    height: auto !important;
    border-radius: 10px !important;
    width: 100%;
}

/* Увеличиваем заголовок Expander */
div[data-testid="stExpander"] details summary p {
    font-size: 20px !important;
    font-weight: 600 !important;
}
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# РЕЖИМ 1: Heatmap
# ==============================================================================
if app_mode == "Heatmap Ошибок":
    st.title("Heatmap Ошибок", text_alignment="center")

    file_path = "uart_final_summary.txt"

    # Инициализация
    addresses = []
    writes_data = []
    reads_data = []
    errors_data = [] 
    error_names = ["RO Denied", "Mismatch", "Sticky", "Deadlock", "Overflow", "Unexp"]
    summary_lines = []

    # Заглушка
    if not os.path.exists(file_path):
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("Header info...\n")
                f.write("Адрес    | Wr | Rd | RO | Mm | St | Dl | Ov | Un |\n")
                f.write("----------+----+----+----+----+----+----+----+----+\n")
                f.write("0x00001000| AA | BB | 0  | 5  | 0  | 0  | 0  | 0  |\n")
                f.write("0x00001004| CC | DD | 2  | 0  | 1  | 0  | 0  | 0  |\n")
                f.write("0x00001008| EE | FF | 0  | 0  | 0  | 0  | 0  | 0  |\n")
        except:
            pass

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        is_parsing_table = False
        
        for line in lines:
            line = line.strip()
            if not line: continue
            if "Адрес" in line and "|" in line:
                is_parsing_table = True
                continue
            if "-----" in line: continue
            
            if not is_parsing_table:
                summary_lines.append(line)
            else:
                if line.startswith("0x"):
                    parts = [p.strip() for p in line.split('|')]
                    if len(parts) >= 9:
                        addresses.append(parts[0])
                        writes_data.append(parts[1])
                        reads_data.append(parts[2])
                        row_bugs = [int(parts[i]) for i in range(3, 9)]
                        errors_data.append(row_bugs)

    except FileNotFoundError:
        st.error(f"Файл {file_path} не найден!")
        st.stop()
    except Exception as e:
        st.error(f"Ошибка при чтении файла: {e}")
        st.stop()

    if summary_lines:
        with st.expander("Сводная статистика"):
            st.code("\n".join(summary_lines), language="text")

    if not addresses:
        st.info("Данные не найдены.")
        st.stop()

    num_registers = len(addresses)
    num_errors = len(error_names)
    
    # NetworkX (хранилище данных)
    G = nx.grid_2d_graph(num_errors, num_registers)
    for x in range(num_errors):
        for y in range(num_registers):
            G.nodes[(x, y)]['freq'] = errors_data[y][x]
            G.nodes[(x, y)]['bug_name'] = error_names[x]

    # Палитры
    green_colors = ["#112a14", "#163619", "#1c431f", "#225025", "#285e2c", "#2e6c32", "#357b39", "#3d8a41", "#449948", "#4ca950", "#54b858", "#61c265", "#70cc73", "#80d582", "#90de91", "#a1e7a2", "#b2efb3", "#c4f6c4", "#d5fcd5", "#e1fde1", "#edffed"]
    red_colors = ["#3a0000", "#4d0000", "#600000", "#730000", "#860000", "#990000", "#ac0000", "#bf0000", "#d20000", "#e60000", "#f90000", "#ff1a1a", "#ff3333", "#ff4d4d", "#ff6666", "#ff8080", "#ff9999", "#ffb3b3", "#ffcccc", "#ffe6e6", "#fff0f0"]
    
    all_bugs_flat = [val for row in errors_data for val in row]
    non_zero_bugs = [b for b in all_bugs_flat if b > 0]
    global_min = min(non_zero_bugs) if non_zero_bugs else 0
    global_max = max(non_zero_bugs) if non_zero_bugs else 1

    # CSS Heatmap
    css = """
    <style>
        .heatmap-container { display: grid; grid-template-columns: 60px 60px 60px repeat(6, 65px); gap: 8px; align-items: center; justify-content: center; position: relative; overflow: visible !important; }
        .grid-header { font-weight: bold; text-align: center; font-size: 13px; color: #e0e0e0; padding-bottom: 5px; line-height: 1.2; }
        .grid-text-cell { font-family: monospace; font-size: 14px; text-align: center; color: #bbb; }
        .grid-address { text-align: right; padding-right: 10px; color: #fff; }
        .cell-wrapper { position: relative; width: 65px; height: 48px; margin: 0; overflow: visible !important; }
        .cell-wrapper:hover { z-index: 1000; }
        .grid-cell { width: 100%; height: 100%; border-radius: 6px; border: 1px solid #444; transition: transform 0.1s ease, box-shadow 0.1s ease; cursor: pointer; }
        .cell-wrapper:hover .grid-cell { transform: scale(1.15); border: 2px solid #fff; box-shadow: 0px 4px 12px rgba(255, 255, 255, 0.3); }
        .grid-cell-empty { background-color: transparent; border: 1px dashed #444; }
        .custom-tooltip { visibility: hidden; background-color: #1a1a1a; color: #ffffff; text-align: center; border-radius: 6px; padding: 8px 12px; position: absolute; bottom: 125%; left: 50%; transform: translateX(-50%); opacity: 0; transition: opacity 0.2s, bottom 0.2s; font-size: 13px; border: 1px solid #555; pointer-events: none; z-index: 99999 !important; white-space: nowrap; }
        .custom-tooltip b { color: #ffab40; }
        .custom-tooltip::after { content: ""; position: absolute; top: 100%; left: 50%; margin-left: -6px; border-width: 6px; border-style: solid; border-color: #555 transparent transparent transparent; }
        .cell-wrapper:hover .custom-tooltip { visibility: visible; opacity: 1; bottom: 135%; }
        .legend-wrapper { display: flex; flex-direction: row; height: 888px; margin-top: 45px; justify-content: center; }
        .legend-color-bar { width: 35px; height: 100%; border-radius: 6px; border: 1px solid #555; }
        .legend-labels-container { position: relative; height: 100%; width: 100px; margin-left: 10px; }
        .legend-label { position: absolute; left: 0; transform: translateY(50%); display: flex; align-items: center; gap: 6px; font-size: 13px; color: #fff; font-family: monospace; font-weight: bold; }
        .legend-arrow { color: #bbb; font-size: 12px; }
    </style>
    """
    
    gradient_green = f"linear-gradient(to top, {', '.join(green_colors)})"
    gradient_red = f"linear-gradient(to top, {', '.join(red_colors)})"

    # Сборка HTML
    html_parts = ['<div style="display:flex; justify-content:center; gap: 50px; margin-top:30px; padding-bottom:80px;">']
    html_parts.append('<div class="heatmap-container">')
    html_parts.append('<div></div><div class="grid-header" style="color:#aaa; align-self:end;">Writes</div><div class="grid-header" style="color:#aaa; align-self:end;">Reads</div>')
    
    for name in error_names:
        html_parts.append(f'<div class="grid-header" style="align-self:end;">{name.replace(" ", "<br>")}</div>')

    for y in range(num_registers):
        html_parts.append(f'<div class="grid-text-cell grid-address">{addresses[y]}</div>')
        html_parts.append(f'<div class="grid-text-cell">{writes_data[y]}</div>')
        html_parts.append(f'<div class="grid-text-cell">{reads_data[y]}</div>')
        
        for x in range(num_errors):
            node = G.nodes[(x, y)]
            freq = node['freq']
            bug = node['bug_name']
            
            title = f"{bug}: {freq}"
            html_parts.append(f'<div class="cell-wrapper" title="{title}">')
            if freq == 0:
                html_parts.append('<div class="grid-cell grid-cell-empty"></div>')
                html_parts.append(f'<span class="custom-tooltip"><b>{bug}</b><br>Ошибок нет</span>')
            else:
                ratio = (freq - global_min) / (global_max - global_min) if global_max > global_min else 1.0
                palette = green_colors if bug == "RO Denied" else red_colors
                hex_c = palette[int(round(ratio * (len(palette) - 1)))]
                html_parts.append(f'<div class="grid-cell" style="background-color: {hex_c};"></div>')
                html_parts.append(f'<span class="custom-tooltip"><b>{bug}</b><br>Количество: {freq}</span>')
            html_parts.append('</div>')
    
    html_parts.append('</div>') 

    # Легенда
    html_parts.append('<div class="legend-wrapper">')
    html_parts.append(f'<div class="legend-color-bar" style="background: {gradient_green};"></div>')
    html_parts.append(f'<div class="legend-color-bar" style="background: {gradient_red}; margin-left: 8px;"></div>')
    html_parts.append('<div class="legend-labels-container">')
    
    leg_vals = set([global_min, global_max])
    step = max(1, int(global_max / 40))
    if step > 5: step = (step // 5) * 5 
    
    for v in range(0, global_max + 1, step):
        if v > global_min and v < global_max: leg_vals.add(v)
        
    for val in sorted(list(leg_vals)):
        pct = (val - global_min) / (global_max - global_min) * 100 if global_max > global_min else 100
        html_parts.append(f'<div class="legend-label" style="bottom: {pct}%;"><span class="legend-arrow">◀</span> {val}</div>')
    
    html_parts.append('</div></div></div>')
    
    st.markdown(css + "".join(html_parts), unsafe_allow_html=True)

# ==============================================================================
# РЕЖИМ 2: Оценка Pylint
# ==============================================================================
elif app_mode == "Оценка Pylint":
    st.title("Оценка Pylint", text_alignment="center")

    file_to_check = "golden_tester.py"
    
    if not os.path.exists(file_to_check):
        with open(file_to_check, "w") as f:
            f.write("import os\n\ndef my_func():\n    x = 1\n    return x\n")

    col_l, col_c, col_r = st.columns([1, 2, 1])
    
    with col_c:
        run_btn = st.button("ЗАПУСТИТЬ PYLINT", use_container_width=True)
    
    if run_btn:
        with st.spinner("Анализ кода..."):
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pylint", file_to_check],
                    capture_output=True,
                    text=True
                )
                output = result.stdout
                
                score_match = re.search(r"rated at (-?\d+\.?\d*)/10", output)
                
                if score_match:
                    score = score_match.group(1)
                    html_score = (
                        f'<div style="display: flex; align-items: center; justify-content: center; margin-top: 40px; margin-bottom: 40px; padding: 30px; background-color: #0e1117; border-radius: 15px; border: 1px solid #333;">'
                        f'<div style="width: 30px; height: 30px; background-color: #4ca950; border-radius: 50%; margin-right: 25px; box-shadow: 0 0 15px rgba(76, 169, 80, 0.6);"></div>'
                        f'<div style="font-size: 72px; font-weight: 700; color: #ffffff; font-family: sans-serif; line-height: 1;">{score}/10</div>'
                        f'</div>'
                    )
                    st.markdown(html_score, unsafe_allow_html=True)
                else:
                    st.warning("Не удалось найти оценку в выводе Pylint.")
                
                with st.expander("Показать полный лог"):
                    st.code(output, language="text")
                    if result.stderr:
                        st.error(result.stderr)
            except Exception as e:
                st.error(f"Ошибка при запуске: {e}")

# ==============================================================================
# РЕЖИМ 3: Покрытие 
# ==============================================================================
elif app_mode == "Покрытие":
    st.title("Тестовое покрытие", text_alignment="center")

    test_file = "golden_tester.py"
    
    # Создаем фиктивный тест, если нет, чтобы кнопка работала
    if not os.path.exists(test_file):
        with open(test_file, "w") as f:
            f.write("import unittest\n\nclass TestF(unittest.TestCase):\n    def test_pass(self):\n        self.assertEqual(1, 1)\n")
            
    col_l, col_c, col_r = st.columns([1, 2, 1])
    
    with col_c:
        # Кнопка по центру, такая же большая
        run_cov_btn = st.button("ЗАПУСТИТЬ PYTEST (COV)", use_container_width=True)

    if run_cov_btn:
        with st.spinner("Запуск тестов и расчет покрытия..."):
            try:
                # Запускаем pytest с модулем Покрытие
                # ВАЖНО: Требуется установленный пакет pytest-cov
                # Команда: python -m pytest --cov=. test_f2.py
                cmd = [sys.executable, "-m", "pytest", "--cov=riscv_br", test_file]
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True
                )
                
                output = result.stdout + "\n" + result.stderr
                
                # Попытка найти процент покрытия в выводе
                # Обычно строка выглядит как: TOTAL      20      5    75%
                cov_match = re.search(r"TOTAL\s+.*\s+(\d+)%", output)
                
                if cov_match:
                    cov_percent = int(cov_match.group(1))
                    
                    # Определение цвета круга
                    # Красный < 50, Желтый < 80, Зеленый >= 80
                    if cov_percent < 50:
                        circle_color = "#e74c3c" # Red
                    elif cov_percent < 80:
                        circle_color = "#f1c40f" # Yellow
                    else:
                        circle_color = "#4ca950" # Green
                    
                    # HTML/CSS для круга (Donut Chart)
                    # Используем conic-gradient для заливки
                    html_circle = (
                        f'<div style="display: flex; justify-content: center; margin-top: 40px; margin-bottom: 40px;">'
                        f'<div style="'
                        f'width: 250px; height: 250px; '
                        f'border-radius: 50%; '
                        f'background: conic-gradient({circle_color} {cov_percent}%, #333333 {cov_percent}% 100%); '
                        f'display: flex; align-items: center; justify-content: center; '
                        f'box-shadow: 0 0 20px rgba(0,0,0,0.5);'
                        f'">'
                        f'  <div style="'
                        f'  width: 200px; height: 200px; '
                        f'  background-color: #0e1117; '
                        f'  border-radius: 50%; '
                        f'  display: flex; align-items: center; justify-content: center;'
                        f'  ">'
                        f'      <span style="font-size: 64px; font-weight: bold; color: {circle_color}; font-family: sans-serif;">'
                        f'      {cov_percent}%'
                        f'      </span>'
                        f'  </div>'
                        f'</div>'
                        f'</div>'
                    )
                    
                    st.markdown(html_circle, unsafe_allow_html=True)
                
                else:
                    st.warning("Не удалось определить процент покрытия. Убедитесь, что установлен 'pytest-cov'.")
                    st.info("Попробуйте выполнить: pip install pytest-cov")

                # Логи
                with st.expander("Показать полный лог тестов"):
                    st.code(output, language="text")

            except Exception as e:
                st.error(f"Ошибка при запуске: {e}")