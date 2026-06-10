import streamlit as st
import pandas as pd
import random
import os
import time

st.set_page_config(page_title="世界遺産検定 演習・試験システム", layout="centered")

# --- カスタムCSS（チェックボックス選択時に色を変えるUIなど） ---
st.markdown("""
<style>
    .stButton > button {
        border-radius: 8px;
        padding: 0.5rem 1rem;
        text-align: left !important;
        justify-content: flex-start !important;
    }
    .selected-box {
        background-color: #e8f4fd;
        border: 2px solid #2196f3;
        border-radius: 8px;
        padding: 10px;
        margin-bottom: 5px;
    }
    .unselected-box {
        background-color: #f9f9f9;
        border: 1px solid #ddd;
        border-radius: 8px;
        padding: 10px;
        margin-bottom: 5px;
    }
</style>
""", unsafe_allow_html=True)

# --- 1. 共通ユーティリティ ---
def get_safe_value(row, col_name):
    if col_name not in row: return ""
    val = row.get(col_name)
    if isinstance(val, pd.Series): val = val.iloc[0]
    s_val = str(val).strip()
    if pd.isna(val) or s_val.lower() == "nan" or s_val == "" or s_val == "/": return ""
    return s_val

def split_items(text):
    if not text: return []
    return [i.strip() for i in text.replace('/', '\n').split('\n') if i.strip()]

# --- 2. データのロード環境 ---
@st.cache_data(show_spinner=False)
def load_all_data(grade):
    # 💡 ここにGitHubで取得した「Raw」のURLをそのまま貼り付けてください
    p = "https://github.com/ChocoIce3491/my-server/raw/refs/heads/main/%E4%B8%96%E7%95%8C%E9%81%BA%E7%94%A3/quiz/quiz_level1_data.csv"
    
    # 万が一、URLが貼り付けられていない場合のセーフティ
    if "http" not in p:
        p = "quiz_level1_data.csv"
        
    for encoding in ['utf-8-sig', 'utf-8', 'cp932', 'shift_jis']:
        try:
            df = pd.read_csv(p, encoding=encoding)
            df.columns = df.columns.str.strip()
            if '地域' not in df.columns:
                df['地域'] = "大分類"
            return df.dropna(subset=['名称']).reset_index(drop=True)
        except:
            continue
            
    return pd.DataFrame()

# --- 3. ダミー選択肢生成 ---
def get_dummy_options(df_all, target_col, forbidden_list, row_info, num=3):
    filters = []
    if '章' in df_all.columns and '章' in row_info and get_safe_value(row_info, '章'):
        filters.append(df_all['章'] == row_info['章'])
    if '地域' in df_all.columns and '地域' in row_info and get_safe_value(row_info, '地域'):
        filters.append(df_all['地域'] == row_info['地域'])

    candidates = []
    for f in filters:
        subset = df_all[f]
        if target_col in subset.columns:
            vals = []
            for v in subset[target_col].dropna():
                vals.extend([i for i in split_items(str(v)) if i not in forbidden_list])
            candidates.extend(list(set(vals)))
            if len(set(candidates)) >= num: break
    
    if len(set(candidates)) < num and target_col in df_all.columns:
        for v in df_all[target_col].dropna():
            candidates.extend([i for i in split_items(str(v)) if i not in forbidden_list])
            
    final_cands = list(set(candidates))
    random.shuffle(final_cands)
    return final_cands[:num] if len(final_cands) >= num else (final_cands + ["ダミー選択肢"] * num)[:num]

# --- 4. クイズ生成エンジン ---
def build_quiz_session(df_pool, df_all, is_exam=False, limit=60):
    if df_pool.empty:
        return []
        
    raw_quiz_list = []
    indices = df_pool.index.tolist()
    
    target_cols = ['時代・王朝', '時代', '人種・民族', '民族', '政治家', '芸術家', '人', '生物', '植物', '美術品', '建築・絵画の様式', '文化', '宗教', 'バイオーム', '特徴', '都市']
    actual_cols = [c for c in target_cols if c in df_pool.columns]

    for idx in indices:
        row = df_pool.loc[idx]
        heritage_name = get_safe_value(row, '名称')
        
        available_cols = [c for c in actual_cols if get_safe_value(row, c)]
        if available_cols:
            sel_col = random.choice(available_cols)
            val_str = get_safe_value(row, sel_col)
            items = split_items(val_str)
            
            if len(items) >= 3:
                ans = get_dummy_options(df_all, sel_col, items, row, 1)[0]
                wrong_opts = random.sample(items, 3)
                opts = wrong_opts + [ans]
                random.shuffle(opts)
                q_text = f"遺産「**{heritage_name}**」の **{sel_col}** として【正しくないもの】は？"
                raw_quiz_list.append({"q": q_text, "ans": [ans], "opts": opts, "info": row, "mode": "single_negative"})
                
            elif len(items) == 2:
                ans_list = items
                dummies = get_dummy_options(df_all, sel_col, ans_list, row, 3)
                opts = ans_list + dummies
                random.shuffle(opts)
                q_text = f"遺産「**{heritage_name}**」に合致する **{sel_col}** を【2つ】選んでください。"
                raw_quiz_list.append({"q": q_text, "ans": ans_list, "opts": opts, "info": row, "mode": "multi_select"})
                
            else:
                ans = items[0]
                dummies = get_dummy_options(df_all, sel_col, items, row, 3)
                opts = [ans] + dummies
                random.shuffle(opts)
                q_text = f"遺産「**{heritage_name}**」に合致する **{sel_col}** は？"
                raw_quiz_list.append({"q": q_text, "ans": [ans], "opts": opts, "info": row, "mode": "single_positive"})

        # --- 【構成資産問】ランダム1択化（単体出題対応） ---
        c_name = get_safe_value(row, '構成資産')
        c_detail = get_safe_value(row, '構成資産の詳細')
        
        if c_name:
            n_list = split_items(c_name)
            d_list = split_items(c_detail)
            valid_indices = [i for i, n in enumerate(n_list) if n]
            
            if valid_indices:
                chosen_idx = random.choice(valid_indices)
                chosen_n = n_list[chosen_idx]
                chosen_d = d_list[chosen_idx] if chosen_idx < len(d_list) else ""
                
                if chosen_d:
                    c_dummies = get_dummy_options(df_all, '構成資産の詳細', d_list, row, 3)
                    c_opts = [chosen_d] + c_dummies
                    random.shuffle(c_opts)
                    raw_quiz_list.append({
                        "q": f"構成資産「**{chosen_n}**」に合致する詳細は？",
                        "ans": [chosen_d], "opts": c_opts, "info": row, "mode": "single_positive", "is_asset_of": idx
                    })
                else:
                    c_dummies = get_dummy_options(df_all, '構成資産', n_list, row, 3)
                    c_opts = [chosen_n] + c_dummies
                    random.shuffle(c_opts)
                    raw_quiz_list.append({
                        "q": f"遺産「**{heritage_name}**」に合致する【構成資産】は？",
                        "ans": [chosen_n], "opts": c_opts, "info": row, "mode": "single_positive", "is_asset_of": idx
                    })

    grouped_quizzes = {}
    for q in raw_quiz_list:
        ref_idx = q['is_asset_of'] if 'is_asset_of' in q else q['info'].name
        if ref_idx not in grouped_quizzes:
            grouped_quizzes[ref_idx] = {'basic': None, 'asset': None}
        if 'is_asset_of' in q:
            grouped_quizzes[ref_idx]['asset'] = q
        else:
            grouped_quizzes[ref_idx]['basic'] = q

    group_keys = list(grouped_quizzes.keys())
    random.shuffle(group_keys)

    final_quiz_list = []
    for k in group_keys:
        group = grouped_quizzes[k]
        if group['basic']: final_quiz_list.append(group['basic'])
        if group['asset']: final_quiz_list.append(group['asset'])

    if is_exam: return final_quiz_list[:limit]
    return final_quiz_list

# --- 5. アプリケーションコントロール ---
st.sidebar.title("🎓 世界遺産検定システム")
app_mode = st.sidebar.radio("モード選択", ["演習モード", "試験モード"])
grade = st.sidebar.selectbox("対象の級", ["1級"])

df_master = load_all_data(grade)

# セッション状態の初期化
if "score" not in st.session_state: st.session_state.score = 0
if "wrong_heritage_rows" not in st.session_state: st.session_state.wrong_heritage_rows = []
# ★ 次の章へのスムーズな移行のため、文字列ではなく選択中の「章の名前」を直接ステートに格納
if "current_selected_chap" not in st.session_state: st.session_state.current_selected_chap = "すべて"
if "current_selected_area" not in st.session_state: st.session_state.current_selected_area = "すべて"

with st.sidebar:
    st.write("---")
    if not df_master.empty:
        if app_mode == "演習モード":
            areas = ["すべて"] + list(df_master['地域'].dropna().unique())
            
            # ステートに存在しない地域が選ばれていた場合の安全処理
            if st.session_state.current_selected_area not in areas:
                st.session_state.current_selected_area = "すべて"
            area_idx = areas.index(st.session_state.current_selected_area)
            
            sel_area = st.selectbox("大分類（地域）", areas, index=area_idx)
            st.session_state.current_selected_area = sel_area
            
            df_sub = df_master if sel_area == "すべて" else df_master[df_master['地域'] == sel_area]
            
            chaps = ["すべて"] + list(df_sub['章'].dropna().unique())
            
            # 選択中の章が現在のリスト内に存在するか安全確認
            if st.session_state.current_selected_chap not in chaps:
                st.session_state.current_selected_chap = "すべて"
            chap_idx = chaps.index(st.session_state.current_selected_chap)
            
            # index属性とセッション情報をガッチリ同期させる
            sel_chap = st.selectbox("小分類（章）", chaps, index=chap_idx)
            st.session_state.current_selected_chap = sel_chap
            
            df_target = df_sub if sel_chap == "すべて" else df_sub[df_sub['章'] == sel_chap]
        else:
            df_target = df_master
    else:
        df_target = pd.DataFrame()

    if st.button("クイズを生成 / リセット", type="primary"):
        if df_master.empty:
            st.error("CSVファイルを読み込めていません。")
        else:
            num = 90 if grade == "1級" else 60
            st.session_state.quizzes = build_quiz_session(df_target, df_master, (app_mode=="試験モード"), num)
            st.session_state.q_idx = 0
            st.session_state.answered = False
            st.session_state.selected_options = [] 
            st.session_state.score = 0
            st.session_state.wrong_heritage_rows = []
            st.session_state.start_time = time.time()
            st.rerun()

if df_master.empty:
    st.error("🚨 【データ未検出】CSVファイルがシステムに認識されていません。")
    st.stop()

# --- 6. クイズメイン画面 ---
if "quizzes" in st.session_state and st.session_state.quizzes:
    q_idx = st.session_state.q_idx
    
    # リザルト画面
    if q_idx >= len(st.session_state.quizzes):
        st.balloons()
        st.write("## 🏁 全ての出題が完了しました！")
        
        total_q = len(st.session_state.quizzes)
        correct_q = st.session_state.score
        accuracy = (correct_q / total_q) * 100 if total_q > 0 else 0
        
        st.metric(label="🏆 今回の正解率", value=f"{correct_q} / {total_q} 問", delta=f"{accuracy:.1f} %")
        
        if accuracy >= 70:
            st.success(f"🎉 合格ライン（7割）を突破しています！この調子です！")
        else:
            st.warning(f"💪 あと一歩！間違えた問題を復習して記憶を完璧にしましょう。")
            
        st.write("---")
        
        col1, col2 = st.columns(2)
        
        with col1:
            has_wrong = len(st.session_state.wrong_heritage_rows) > 0
            if st.button("❌ 間間違えた問題を復習する", use_container_width=True, type="secondary", disabled=not has_wrong):
                df_wrong_pool = pd.DataFrame(st.session_state.wrong_heritage_rows).drop_duplicates(subset=['名称'])
                st.session_state.quizzes = build_quiz_session(df_wrong_pool, df_master, is_exam=False)
                st.session_state.q_idx = 0
                st.session_state.answered = False
                st.session_state.selected_options = []
                st.session_state.score = 0
                st.session_state.wrong_heritage_rows = []
                st.rerun()
            if not has_wrong:
                st.caption("満点です！復習する問題はありません。")
                
        with col2:
            # 【エラー原因修正箇所】「次の章に進む」ボタンのステート制御を安全化
            if app_mode == "演習モード" and st.session_state.current_selected_chap != "すべて":
                current_chap = st.session_state.current_selected_chap
                sel_area = st.session_state.current_selected_area
                df_sub_area = df_master if sel_area == "すべて" else df_master[df_master['地域'] == sel_area]
                all_chaps = list(df_sub_area['章'].dropna().unique())
                
                if current_chap in all_chaps:
                    current_idx = all_chaps.index(current_chap)
                    if current_idx + 1 < len(all_chaps):
                        next_chap_name = all_chaps[current_idx + 1]
                        if st.button(f"➡️ 次の章（{next_chap_name}）に進む", use_container_width=True, type="primary"):
                            # ★直接 st.session_state[key] を弄るのをやめ、連動している状態変数を書き換える
                            st.session_state.current_selected_chap = next_chap_name
                            df_next_target = df_sub_area[df_sub_area['章'] == next_chap_name]
                            
                            # 次の章の問題をあらかじめ自動構築
                            st.session_state.quizzes = build_quiz_session(df_next_target, df_master, is_exam=False)
                            st.session_state.q_idx = 0
                            st.session_state.answered = False
                            st.session_state.selected_options = []
                            st.session_state.score = 0
                            st.session_state.wrong_heritage_rows = []
                            st.rerun()
                    else:
                        st.button("🥇 この地域のすべての章を制覇しました！", use_container_width=True, disabled=True)
            else:
                st.info("💡 演習モードで「特定の章」を選択している場合、ここに次の章へ進むボタンが出現します。")
        st.stop()

    # --- 以下、通常のクイズ出題画面 ---
    quiz = st.session_state.quizzes[q_idx]
    
    if app_mode == "試験モード":
        elapsed = time.time() - st.session_state.start_time
        limit_min = 90 if grade == "1級" else 60
        remaining = max(0, limit_min * 60 - elapsed)
        st.sidebar.subheader(f"⏱ 残り時間: {int(remaining//60):02d}:{int(remaining%60):02d}")
        if remaining <= 0: st.error("🚨 タイムアップです！試験終了。"); st.stop()

    st.write(f"### 問題 {q_idx + 1} / {len(st.session_state.quizzes)}")
    st.info(quiz['q'])

    def check_user_answer(user_ans_list):
        st.session_state.answered = True
        if set(user_ans_list) == set(quiz['ans']):
            st.session_state.score += 1
            st.session_state.is_current_correct = True
        else:
            st.session_state.wrong_heritage_rows.append(quiz['info'])
            st.session_state.is_current_correct = False

    if quiz['mode'] == "multi_select":
        selected_current = []
        for i, opt in enumerate(quiz['opts']):
            is_checked = opt in st.session_state.selected_options
            box_class = "selected-box" if is_checked else "unselected-box"
            
            with st.container():
                st.markdown(f'<div class="{box_class}">', unsafe_allow_html=True)
                cb = st.checkbox(opt, key=f"chk_{q_idx}_{i}", value=is_checked, disabled=st.session_state.answered)
                if cb: selected_current.append(opt)
                st.markdown('</div>', unsafe_allow_html=True)
        
        if not st.session_state.answered and set(selected_current) != set(st.session_state.selected_options):
            st.session_state.selected_options = selected_current
            st.rerun()

        if not st.session_state.answered:
            disabled_submit = len(st.session_state.selected_options) != 2
            if st.button("回答を確定する", type="secondary", disabled=disabled_submit):
                check_user_answer(st.session_state.selected_options)
                st.rerun()
    else:
        for i, opt in enumerate(quiz['opts']):
            st.button(opt, key=f"btn_{q_idx}_{i}", use_container_width=True, 
                      disabled=st.session_state.answered,
                      on_click=lambda o=opt: check_user_answer([o]))

    if st.session_state.answered:
        if st.session_state.get("is_current_correct", False):
            st.success("🎯 正解！")
        else:
            formatted_ans = "、".join(quiz['ans'])
            st.error(f"❌ 不正解... 正解は: 【 {formatted_ans} 】")

        with st.expander("📖 解説：この遺産の詳細データ", expanded=True):
            info = quiz['info']
            cols = ['名称', '国名', '登録基準', '場所', '地域', '章', '時代・王朝', '人種・民族', '民族', '政治家', '芸術家', '人', '生物', '植物', '美術品', '建築・絵画の様式', '文化', '宗教', 'バイオーム', '特徴', '都市']
            for c in cols:
                v = get_safe_value(info, c)
                if v: st.write(f"**{c}**: {v}")
            
            cn = split_items(get_safe_value(info, '構成資産'))
            cd = split_items(get_safe_value(info, '構成資産の詳細'))
            if cn:
                st.write("---")
                st.write("**【構成資産リスト】**")
                for i, n in enumerate(cn):
                    if i < len(cd) and cd[i]:
                        st.write(f"・{n} ➔ {cd[i]}")
                    else:
                        st.write(f"・{n}")

        if st.button("次の問題へ ➡️", type="primary"):
            st.session_state.q_idx += 1
            st.session_state.answered = False
            st.session_state.selected_options = [] 
            st.rerun()
else:
    if not df_master.empty:
        st.info("サイドバーで条件を設定し、「クイズを生成 / リセット」を押してください。")
