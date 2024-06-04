import os
import streamlit as st
import pandas as pd
import numpy as np
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import set_with_dataframe
from dotenv import load_dotenv
from geopy.geocoders import Nominatim
import folium
from streamlit_folium import folium_static
import requests
import streamlit.components.v1 as components

# 環境変数から認証情報を取得
SPREADSHEET_ID = st.secrets["spreadsheet_id"]
SP_SHEET = 'kitasan'  # sheet名

# セッション状態の初期化
if 'show_all' not in st.session_state:
    st.session_state['show_all'] = False  # 初期状態は地図上の物件のみを表示
if 'selected_address' not in st.session_state:
    st.session_state['selected_address'] = None
if 'facility_info' not in st.session_state:
    st.session_state['facility_info'] = None

# 地図上以外の物件も表示するボタンの状態を切り替える関数
def toggle_show_all():
    st.session_state['show_all'] = not st.session_state['show_all']

# スプレッドシートからデータを読み込む関数
def load_data_from_spreadsheet():
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    credentials = Credentials.from_service_account_info(st.secrets["credentials"], scopes=scopes)
    gc = gspread.authorize(credentials)
    sh = gc.open_by_key(SPREADSHEET_ID)
    worksheet = sh.worksheet(SP_SHEET)
    pre_data = worksheet.get_all_values()
    col_name = pre_data[0][:]
    df = pd.DataFrame(pre_data[1:], columns=col_name)
    return df

# データフレームの前処理を行う関数
def preprocess_dataframe(df):
    df['家賃'] = pd.to_numeric(df['家賃'], errors='coerce')
    df = df.dropna(subset=['家賃'])
    return df

# 築年数を処理する関数
def process_construction_year(df):
    df['築年数'] = df['築年数'].apply(lambda x: '新築' if x == '0' or x == 0 else x)
    return df

# 地図を作成し、マーカーを追加する関数
def create_map(filtered_df):
    filtered_df = filtered_df.dropna(subset=['latitude', 'longitude'])
    map_center = [filtered_df['latitude'].mean(), filtered_df['longitude'].mean()]
    m = folium.Map(location=map_center, zoom_start=12)
    for idx, row in filtered_df.iterrows():
        if pd.notnull(row['latitude']) and pd.notnull(row['longitude']):
            facilities_info = row.get('Nearby Facilities', '情報なし')
            popup_html = f"""
            <b>名称:</b> {row['Test Write']}<br>
            <b>アドレス:</b> {row['アドレス']}<br>
            <b>築年数:</b> {row['築年数']}年<br>
            <b>家賃:</b> {row['家賃']}万円<br>
            <b>間取り:</b> {row['間取り']}<br>
            <b>最寄り駅:</b> {row['アクセス①1駅名']}<br>
            <b>徒歩(分):</b> {row['アクセス①1徒歩(分)']}<br>
            <b>周辺施設情報:</b> {facilities_info}<br>
            <a href="{row['物件画像URL']}" target="_blank">物件画像を見る</a><br>
            <a href="{row['間取画像URL']}" target="_blank">間取画像を見る</a>
            """
            popup = folium.Popup(popup_html, max_width=400)
            folium.Marker(
                [row['latitude'], row['longitude']],
                popup=popup
            ).add_to(m)
    return m

def make_image(url):
    return f'<img src="{url}" width="100">'

def make_clickable(address):
    return f'<a href="javascript:void(0);" onclick="handleClick(\'{address}\')">{address}</a>'

# 検索結果を表示する関数
def display_search_results(filtered_df):
    if filtered_df.empty:
        st.write("表示するデータがありません。")
        return
    filtered_df['物件番号'] = range(1, len(filtered_df) + 1)
    filtered_df['物件画像URL'] = filtered_df['物件画像URL'].apply(make_image)
    filtered_df['間取画像URL'] = filtered_df['間取画像URL'].apply(make_image)
    filtered_df = filtered_df.rename(columns={
        'アクセス①1駅名': '最寄り駅',
        'アクセス①1徒歩(分)': '徒歩(分)',
        '物件画像URL': '物件画像',
        '間取画像URL': '間取画像',
        'Test Write': '名称'
    })

    if 'Nearby Facilities' not in filtered_df.columns:
        filtered_df['Nearby Facilities'] = '情報なし'

    display_columns = ['物件番号', '名称', 'アドレス', '築年数', '階数', '家賃', '間取り', "最寄り駅", "徒歩(分)", '物件画像', "間取画像", 'Nearby Facilities']
    filtered_df_display = filtered_df[display_columns]
    st.markdown(filtered_df_display.to_html(escape=False, index=False), unsafe_allow_html=True)
    # JavaScriptを追加してクリックイベントをハンドル
    components.html("""
    <script>
    function handleClick(address) {
        const xhr = new XMLHttpRequest();
        xhr.open("POST", "/_st_fetch_address", true);
        xhr.setRequestHeader("Content-Type", "application/json");
        xhr.onreadystatechange = function () {
            if (xhr.readyState === 4 && xhr.status === 200) {
                const response = JSON.parse(xhr.responseText);
                alert(response.data.message);  // ダイアログで応答を表示
            }
        };
        xhr.send(JSON.stringify({address: address}));
    }
    </script>
    """, height=0)

def translate_facilities_info(facilities_info):
    translation = {
        'supermarket': 'スーパー',
        'hospital': '病院',
        'gym': 'ジム',
        'convenience_store': 'コンビニ'
    }
    translated_info = {}
    for key, value in facilities_info.items():
        translated_key = translation.get(key, key)
        translated_info[translated_key] = [translate_to_japanese(name) for name in value]
    return translated_info

def translate_to_japanese(text):
    # ここに翻訳ロジックを追加
    translations = {
        'SEIJO ISHII atré Ebisu Nishikan': '成城石井アトレ恵比寿西館',
        'Peacock Store Daikanyama': 'ピーコックストア代官山',
        'Sanwa Yutenji Store': '三和祐天寺店',
        'Self-Defense Forces Central Hospital': '自衛隊中央病院',
        'Tokyo Kyōsai Hospital': '東京共済病院',
        'Kosei Chuo Hospital': '厚生中央病院',
        'Megalos Zero Plus Ebisu': 'メガロスゼロプラス恵比寿',
        'Joyful Studio': 'ジョイフルスタジオ',
        'Konami Sports Club Meguro-Aobadai': 'コナミスポーツクラブ目黒青葉台',
        'Cerulean Tower Tokyu Hotel': 'セルリアンタワー東急ホテル',
        'Lawson': 'ローソン',
        '7-Eleven - Naka-Meguro': 'セブンイレブン中目黒'
    }
    return translations.get(text, text)

def main():
    df = load_data_from_spreadsheet()
    df = preprocess_dataframe(df)
    df = process_construction_year(df)

    st.header('最高のレジデンスを見つけたいあなたに')
    st.image('EHF_image4.png')
    st.subheader('さあ始めましょう')

    col1, col2 = st.columns([1, 2])

    with col1:
        area = st.radio('■ エリアを選んでください', df['区'].unique())

    with col2:
        # 家賃範囲選択のスライダーをfloat型で設定し、小数点第一位まで表示
        price_min, price_max = st.slider(
            '■ 家賃範囲 (万円)を設定してください', 
            min_value=float(10), 
            max_value=100.0,  # 最大値を100.0に設定
            value=(float(df['家賃'].min()), min(float(df['家賃'].max()), 100.0)),  # 現在の最大値と100を比較して小さい方を選択
            step=0.5,  # ステップサイズを0.1に設定
            format='%.1f'
        )

    with col2:
        type_options = st.multiselect('■ 間取りを選んでください', df['間取り'].unique(), default=df['間取り'].unique())

    filtered_df = df[(df['区'].isin([area])) & (df['間取り'].isin(type_options))]
    filtered_df = filtered_df[(filtered_df['家賃'] >= price_min) & (filtered_df['家賃'] <= price_max)]
    filtered_count = len(filtered_df)

    filtered_df['latitude'] = pd.to_numeric(filtered_df['latitude'], errors='coerce')
    filtered_df['longitude'] = pd.to_numeric(filtered_df['longitude'], errors='coerce')
    filtered_df2 = filtered_df.dropna(subset=['latitude', 'longitude'])

    col2_1, col2_2 = st.columns([1, 2])

    with col2_2:
        st.write(f"物件検索数: {filtered_count}件 / 全{len(df)}件")

    if col2_1.button('検索する', key='search_button'):
        st.session_state['filtered_df'] = filtered_df
        st.session_state['filtered_df2'] = filtered_df2
        st.session_state['search_clicked'] = True

    if st.session_state.get('search_clicked', False):
        m = create_map(st.session_state.get('filtered_df2', filtered_df2))
        folium_static(m)

    show_all_option = st.radio(
        "■ 表示する物件を選んでください",
        ('地図上の検索物件のみ', 'すべての検索物件'),
        index=0 if not st.session_state.get('show_all', False) else 1,
        key='show_all_option'
    )

    st.session_state['show_all'] = (show_all_option == 'すべての検索物件')

    if st.session_state.get('search_clicked', False):
        if st.session_state['show_all']:
            display_search_results(st.session_state.get('filtered_df', filtered_df))
        else:
            display_search_results(st.session_state.get('filtered_df2', filtered_df2))

if __name__ == "__main__":
    if 'search_clicked' not in st.session_state:
        st.session_state['search_clicked'] = False
    if 'show_all' not in st.session_state:
        st.session_state['show_all'] = False
    main()
