import matplotlib.pyplot as plt
import io
import pandas as pd
import matplotlib
import database as db # Нужно, чтобы узнать общий дефицит, если дневной не задан

plt.style.use('dark_background')
matplotlib.rc('font', family='Arial')

def create_progress_chart(data):
    # data теперь содержит 5 элементов: date, weight, in, out, daily_limit
    if not data: return None

    df = pd.DataFrame(data, columns=['date', 'weight', 'in', 'out', 'daily_limit'])
    
    # --- ОБРАБОТКА ВЕСА ---
    df['weight'] = pd.to_numeric(df['weight'], errors='coerce')
    df.loc[df['weight'] <= 0, 'weight'] = float('nan')
    df['weight'] = df['weight'].interpolate(method='linear').bfill()
    
    df['date_str'] = pd.to_datetime(df['date']).dt.strftime('%d.%m')
    
    # --- ОБРАБОТКА ЛИМИТОВ ---
    # Нам нужно узнать "Эффективный лимит" для каждого дня.
    # Если в базе daily_limit is None (NaN), значит берем стандартный (600).
    # Но стандартный дефицит мы не передали в функцию... Хакнем систему:
    # Просто заполним пропуски числом 600 (или можно передать user_id и запросить).
    # Давай сделаем допущение: если не задано, считаем 600.
    df['deficit'] = df['daily_limit'].fillna(600)
    
    bmr = 1950
    df['total_burn'] = bmr + df['out']
    # ВОТ ОНА - ЛИНИЯ ЦЕЛИ: Расход - Обязательный Дефицит
    df['target_limit'] = df['total_burn'] - df['deficit']

    # --- РИСУЕМ ---
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    
    # 1. График Веса
    if df['weight'].notna().any():
        ax1.plot(df['date_str'], df['weight'], color='#00ffcc', marker='o', linewidth=2, label='Вес')
        for i, val in enumerate(df['weight']):
            if pd.notna(val):
                ax1.annotate(f"{val:.1f}", (i, val), xytext=(0, 10), textcoords='offset points', ha='center', color='white', fontsize=9)
    else:
        ax1.text(0.5, 0.5, "Внеси вес", ha='center', color='gray')

    ax1.set_title('Динамика Веса', fontsize=14, color='white')
    ax1.grid(color='#444444', linestyle='--', linewidth=0.5)
    
    # 2. График Калорий
    bars = ax2.bar(df['date_str'], df['in'], color='#ff9900', alpha=0.7, label='Съел')
    
    # Линия ПОЛНОГО расхода (зеленая пунктирная)
    ax2.plot(df['date_str'], df['total_burn'], color='#00ff00', linestyle='--', linewidth=1, alpha=0.5, label='Расход (В ноль)')
    
    # Линия ЦЕЛИ (Желтая жирная) - это твой потолок
    ax2.plot(df['date_str'], df['target_limit'], color='yellow', linestyle='-', linewidth=2, label='ЛИМИТ (Цель)')

    ax2.set_title('План vs Факт', fontsize=14, color='white')
    ax2.grid(color='#444444', linestyle='--', linewidth=0.5)
    ax2.legend(loc='upper left', fontsize=8)

    # ЛОГИКА ЦВЕТА СТОЛБИКОВ
    for i, bar in enumerate(bars):
        # Если съел больше ЛИМИТА (желтой линии) -> Красный
        if df['in'][i] > df['target_limit'][i]:
            bar.set_color('#ff4444') 
        else:
            bar.set_color('#44ff44') # Зеленый (Красава)

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    return buf