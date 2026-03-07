import streamlit as st
import numpy as np
import plotly.express as px

st.set_page_config(page_title="Memory Map 256x256", layout="wide")

def parse_addresses(addr_string):
    addrs = set()
    for part in addr_string.replace(',', ' ').split():
        try:
            addrs.add(int(part, 0))
        except ValueError:
            pass
    return addrs

@st.cache_data
def generate_heatmap_data(working_addrs, buggy_addrs):
    """
    Генерирует матрицу категорий 256x256:
    0 = Невалидный (Серый/Прозрачный)
    1 = Покрытый (Зеленый)
    2 = Баг (Красный)
    """
    img_matrix = np.zeros((256, 256), dtype=np.uint8)
    hover_text = np.empty((256, 256), dtype=object)

    for r in range(256):
        for c in range(256):
            addr = r * 256 + c
            hover_text[r, c] = f"{hex(addr)}"
            
            if addr in buggy_addrs:
                img_matrix[r, c] = 2  # Категория: Баг
            elif addr in working_addrs:
                img_matrix[r, c] = 1  # Категория: Успех
            else:
                img_matrix[r, c] = 0  # Категория: Невалидный

    return img_matrix, hover_text

# --- ИНТЕРФЕЙС STREAMLIT ---

st.title("🔥 Интерактивная карта регистров (256 × 256)")

st.sidebar.header("Ввод адресов")
st.sidebar.markdown("Введите адреса через пробел или запятую (можно использовать `0x42` или `66`).")

default_working = " ".join([hex(i) for i in range(0x00, 0x13)]) + " " + " ".join([hex(i) for i in range(0x14, 0x42)])
default_buggy = "0x42, 0x13"

working_input = st.sidebar.text_area("✅ Покрытые адреса (Зеленые):", value=default_working, height=150)
buggy_input = st.sidebar.text_area("🐞 Адреса с багами (Красные):", value=default_buggy, height=100)

working_addrs = parse_addresses(working_input)
buggy_addrs = parse_addresses(buggy_input)

st.info("💡 **Управление масштабом:** Наведите курсор на нужный участок и **крутите колесико мыши** — зум будет работать точно в место курсора. Для сброса масштаба дважды кликните по карте.")

hide_invalid = st.toggle("👁️ **Скрыть невалидные регистры**", value=False)

col1, col2, col3 = st.columns(3)
col1.metric("✅ Покрыто", len(working_addrs))
col2.metric("🐞 Найдено багов", len(buggy_addrs))
col3.metric("⬜ Невалидных регистров", (256 * 256) - len(working_addrs) - len(buggy_addrs))

with st.spinner('Отрисовка тепловой карты...'):
    img, hover_data = generate_heatmap_data(working_addrs, buggy_addrs)
    
    # Определяем цвета
    COLOR_WORK = "rgba(0, 204, 102, 1)"
    COLOR_BUG  = "rgba(255, 75, 75, 1)"
    # Если скрыты - прозрачный, иначе насыщенный серый
    COLOR_INV  = "rgba(0, 0, 0, 0)" if hide_invalid else "rgba(140, 140, 140, 1)"
    
    # Дискретная шкала для четкого соответствия (0, 1, 2 -> Цвета)
    colorscale =[
        [0.00, COLOR_INV],[0.33, COLOR_INV],[0.33, COLOR_WORK],[0.66, COLOR_WORK],[0.66, COLOR_BUG],[1.00, COLOR_BUG]
    ]
    
    # Создаем график. aspect='auto' позволяет ловить фокус зума без "уплывания" графика
    fig = px.imshow(
        img, 
        color_continuous_scale=colorscale, 
        range_color=[0, 2],
        aspect="auto" 
    )
    
    # Добавляем физический пробел в 1 пиксель между ячейками (xgap, ygap)
    fig.update_traces(
        customdata=hover_data,
        hovertemplate="<b>Адрес:</b> %{customdata}<extra></extra>",
        xgap=1,
        ygap=1  
    )
    
    fig.update_layout(
        xaxis=dict(
            visible=True, showticklabels=False, zeroline=False,
            linecolor='#888888', linewidth=2, mirror=True,
            showgrid=False,             # Отключаем старую сетку
            range=[-0.5, 255.5],        # Стартовый размер строго по матрице
            minallowed=-0.5,            # ЖЕСТКИЙ ЛИМИТ: Запрет зума наружу
            maxallowed=255.5            # ЖЕСТКИЙ ЛИМИТ: Запрет зума наружу
        ),
        yaxis=dict(
            visible=True, showticklabels=False, zeroline=False,
            linecolor='#888888', linewidth=2, mirror=True,
            showgrid=False,             # Отключаем старую сетку
            range=[-0.5, 255.5],        # Стартовый размер строго по матрице
            minallowed=-0.5,            # ЖЕСТКИЙ ЛИМИТ: Запрет зума наружу
            maxallowed=255.5            # ЖЕСТКИЙ ЛИМИТ: Запрет зума наружу
        ),
        coloraxis_showscale=False,      # Скрываем боковую панель цветов (colorbar)
        margin=dict(l=30, r=30, t=30, b=30),
        height=900,
        hovermode="closest",
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        dragmode='zoom'
    )
    
    st.plotly_chart(
        fig, 
        use_container_width=True, 
        config={
            'scrollZoom': True,
            'displayModeBar': True,
            'displaylogo': False,
            'modeBarButtonsToRemove':['lasso2d', 'select2d']
        }
    )