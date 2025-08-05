import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import plotly.express as px
import os

DATA_PATH = "data/equipment.csv"
IMG_DIR = "data/images"

st.set_page_config(page_title="Домашній ППР", page_icon="🛠️", layout="wide")

@st.cache_data
def load_data(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        pd.DataFrame(columns=[
            "id","name","model","serial","last_service_date","interval_days",
            "consumables","notes","photo","status"
        ]).to_csv(path, index=False)
    df = pd.read_csv(path)
    # ensure types
    if "id" not in df.columns or df["id"].isnull().all():
        df["id"] = range(1, len(df) + 1)
    df["interval_days"] = pd.to_numeric(df.get("interval_days", 0), errors="coerce").fillna(0).astype(int)
    # parse dates
    df["last_service_date"] = pd.to_datetime(df.get("last_service_date"), errors="coerce")
    return df

def save_data(df: pd.DataFrame, path: str):
    df.to_csv(path, index=False)
    load_data.clear()

def next_service_date(row) -> datetime:
    if pd.isna(row["last_service_date"]) or row["interval_days"] <= 0:
        return None
    return row["last_service_date"] + timedelta(days=int(row["interval_days"]))

def days_to_next(d):
    if d is None:
        return None
    return (d.date() - datetime.today().date()).days

df = load_data(DATA_PATH)

# Compute next service
df["next_service_date"] = df.apply(next_service_date, axis=1)
df["days_to_next"] = df["next_service_date"].apply(days_to_next)

st.title("🛠️ Домашній ППР — облік обладнання, витратників і нагадування")

# Sidebar filters
st.sidebar.header("Фільтри")
status_filter = st.sidebar.multiselect("Статус", ["active","archived"], default=["active"])
days_range = st.sidebar.slider("Показати задачі на N днів вперед", 0, 365, 60)
search = st.sidebar.text_input("Пошук", placeholder="Назва / модель / серійний номер")

filtered = df[df["status"].isin(status_filter)].copy()
if search:
    s = search.lower()
    filtered = filtered[
        filtered["name"].str.lower().str.contains(s, na=False) |
        filtered["model"].str.lower().str.contains(s, na=False) |
        filtered["serial"].str.lower().str.contains(s, na=False) |
        filtered["consumables"].str.lower().str.contains(s, na=False) |
        filtered["notes"].str.lower().str.contains(s, na=False)
    ]

# Upcoming tasks
today = datetime.today().date()
horizon = today + timedelta(days=days_range)
upcoming = filtered.copy()
upcoming = upcoming[~upcoming["next_service_date"].isna()]
upcoming = upcoming[(upcoming["next_service_date"].dt.date >= today) & (upcoming["next_service_date"].dt.date <= horizon)]
overdue = filtered.copy()
overdue = overdue[~overdue["next_service_date"].isna()]
overdue = overdue[overdue["next_service_date"].dt.date < today]

col1, col2, col3 = st.columns(3)
col1.metric("Активних позицій", int((df["status"]=="active").sum()))
col2.metric("Наближається робіт", len(upcoming))
col3.metric("Прострочених", len(overdue))

with st.expander("📅 Найближчі роботи", expanded=True):
    st.dataframe(
        upcoming.sort_values("next_service_date")[["id","name","model","consumables","last_service_date","interval_days","next_service_date","days_to_next"]]
        .rename(columns={
            "name":"Назва","model":"Модель","consumables":"Витратники",
            "last_service_date":"Останнє обслуговування","interval_days":"Інтервал (дні)",
            "next_service_date":"Наступне обслуговування","days_to_next":"Днів залишилось"
        }),
        use_container_width=True
    )

with st.expander("⛔ Прострочені", expanded=False):
    st.dataframe(
        overdue.sort_values("next_service_date")[["id","name","model","consumables","last_service_date","interval_days","next_service_date","days_to_next"]]
        .rename(columns={
            "name":"Назва","model":"Модель","consumables":"Витратники",
            "last_service_date":"Останнє обслуговування","interval_days":"Інтервал (дні)",
            "next_service_date":"Наступне обслуговування","days_to_next":"Днів прострочки"
        }),
        use_container_width=True
    )

# Chart
chart_df = filtered.copy()
chart_df = chart_df.dropna(subset=["next_service_date"])
if not chart_df.empty:
    chart_df["month"] = chart_df["next_service_date"].dt.to_period("M").dt.to_timestamp()
    monthly = chart_df.groupby("month").size().reset_index(name="tasks")
    fig = px.bar(monthly, x="month", y="tasks", title="Кількість робіт за місяцями (на горизонті фільтра)")
    st.plotly_chart(fig, use_container_width=True)

st.markdown("---")

# Tabs
tab_list, tab_add, tab_edit, tab_export = st.tabs(["📋 Список обладнання", "➕ Додати обладнання", "✏️ Позначити виконання/редагувати", "📤 Експорт нагадувань (.ics)"])

with tab_list:
    st.subheader("Обладнання")
    st.dataframe(
        filtered.sort_values("name")[["id","name","model","serial","consumables","last_service_date","interval_days","next_service_date","status"]]
        .rename(columns={
            "id":"ID","name":"Назва","model":"Модель","serial":"Серійний №",
            "consumables":"Витратники","last_service_date":"Останнє обслуговування",
            "interval_days":"Інтервал (дні)","next_service_date":"Наступне обслуговування",
            "status":"Статус"
        }),
        use_container_width=True
    )

with tab_add:
    st.subheader("Додати обладнання")
    with st.form("add_form", clear_on_submit=True):
        name = st.text_input("Назва *")
        model = st.text_input("Модель")
        serial = st.text_input("Серійний №")
        last_service = st.date_input("Дата останнього обслуговування", value=datetime.today())
        interval_days = st.number_input("Інтервал (дні) *", min_value=0, value=180, step=1)
        consumables = st.text_area("Витратники (через ;)", placeholder="фільтр; масло; прокладка")
        notes = st.text_area("Нотатки")
        photo = st.file_uploader("Фото (опційно)", type=["png","jpg","jpeg"], accept_multiple_files=False)
        status = st.selectbox("Статус", ["active","archived"], index=0)
        submitted = st.form_submit_button("Додати")
        if submitted:
            new_id = (df["id"].max() + 1) if len(df) else 1
            photo_path = ""
            if photo is not None:
                os.makedirs(IMG_DIR, exist_ok=True)
                photo_path = os.path.join(IMG_DIR, f"{new_id}_{photo.name}")
                with open(photo_path, "wb") as out:
                    out.write(photo.getbuffer())
            new_row = {
                "id": int(new_id),
                "name": name.strip(),
                "model": model.strip(),
                "serial": serial.strip(),
                "last_service_date": pd.to_datetime(last_service),
                "interval_days": int(interval_days),
                "consumables": consumables.strip(),
                "notes": notes.strip(),
                "photo": photo_path,
                "status": status
            }
            df_new = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            # save with ISO date
            df_to_save = df_new.copy()
            df_to_save["last_service_date"] = df_to_save["last_service_date"].dt.strftime("%Y-%m-%d")
            save_data(df_to_save, DATA_PATH)
            st.success("Додано! Оновіть сторінку, щоб побачити запис у списку.")

with tab_edit:
    st.subheader("Позначити виконання або змінити дані")
    ids = filtered["id"].tolist()
    if ids:
        selected_id = st.selectbox("Оберіть ID обладнання", ids)
        row = df[df["id"]==selected_id].iloc[0]
        st.write(f"**{row['name']}** — наступне обслуговування: {row['next_service_date'].date() if pd.notna(row['next_service_date']) else '—'}")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("✅ Позначити обслуговування виконаним (оновити дату на сьогодні)"):
                df.loc[df["id"]==selected_id, "last_service_date"] = pd.to_datetime(datetime.today().date())
                df_to_save = df.copy()
                df_to_save["last_service_date"] = df_to_save["last_service_date"].dt.strftime("%Y-%m-%d")
                save_data(df_to_save, DATA_PATH)
                st.success("Оновлено дату останнього обслуговування.")
        with c2:
            if st.button("🗃️ Архівувати / Розархівувати"):
                df.loc[df["id"]==selected_id, "status"] = "archived" if row["status"]=="active" else "active"
                df_to_save = df.copy()
                df_to_save["last_service_date"] = df_to_save["last_service_date"].dt.strftime("%Y-%m-%d")
                save_data(df_to_save, DATA_PATH)
                st.success("Статус змінено.")

        st.markdown("---")
        with st.form("edit_form"):
            name_e = st.text_input("Назва", value=row["name"])
            model_e = st.text_input("Модель", value=row["model"])
            serial_e = st.text_input("Серійний №", value=row["serial"])
            last_service_e = st.date_input("Дата останнього обслуговування", value=row["last_service_date"] if pd.notna(row["last_service_date"]) else datetime.today())
            interval_days_e = st.number_input("Інтервал (дні)", min_value=0, value=int(row["interval_days"]))
            consumables_e = st.text_area("Витратники (через ;)", value=row["consumables"] or "")
            notes_e = st.text_area("Нотатки", value=row["notes"] or "")
            status_e = st.selectbox("Статус", ["active","archived"], index=0 if row["status"]=="active" else 1)
            submitted_e = st.form_submit_button("Зберегти зміни")
            if submitted_e:
                df.loc[df["id"]==selected_id, ["name","model","serial","last_service_date","interval_days","consumables","notes","status"]] = [
                    name_e, model_e, serial_e, pd.to_datetime(last_service_e), int(interval_days_e), consumables_e, notes_e, status_e
                ]
                df_to_save = df.copy()
                df_to_save["last_service_date"] = df_to_save["last_service_date"].dt.strftime("%Y-%m-%d")
                save_data(df_to_save, DATA_PATH)
                st.success("Зміни збережено.")

    else:
        st.info("Записів не знайдено. Додайте обладнання на вкладці 'Додати'.")

with tab_export:
    st.subheader("Експорт найближчих робіт у .ics")
    horizon_days = st.number_input("Горизонт (днів)", min_value=1, value=60, step=1)
    upc = df.copy()
    upc["next_service_date"] = upc.apply(lambda r: r["last_service_date"] + pd.Timedelta(days=int(r["interval_days"])) if pd.notna(r["last_service_date"]) and int(r["interval_days"])>0 else pd.NaT, axis=1)
    upc = upc.dropna(subset=["next_service_date"])
    end_date = datetime.today().date() + timedelta(days=int(horizon_days))
    upc = upc[(upc["next_service_date"].dt.date >= today) & (upc["next_service_date"].dt.date <= end_date)]
    if upc.empty:
        st.info("Немає подій для експорту в заданому горизонті.")
    else:
        # Build ICS content
        def ics_escape(text: str) -> str:
            return text.replace(",", "\,").replace(";", "\;")
        lines = ["BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//Home PPR//UA//EN"]
        for _, r in upc.iterrows():
            dt = r["next_service_date"]
            dtstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
            dtstart = dt.strftime("%Y%m%d")
            summary = f"PPR: {r['name']}"
            description = f"Модель: {r['model']}\nВитратники: {r['consumables']}\nНотатки: {r['notes']}"
            uid = f"{r['id']}@home-ppr.local"
            lines += [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{dtstamp}",
                f"DTSTART;VALUE=DATE:{dtstart}",
                f"SUMMARY:{ics_escape(summary)}",
                f"DESCRIPTION:{ics_escape(description)}",
                "END:VEVENT"
            ]
        lines.append("END:VCALENDAR")
        ics_content = "\n".join(lines)
        st.download_button("Завантажити .ics", data=ics_content, file_name="home_ppr_reminders.ics", mime="text/calendar")
        st.caption("Імпортуйте файл у Google Calendar / Apple Calendar / Outlook.")

st.markdown("---")
st.caption("Зроблено для персонального використання: керуйте ППР у браузері або на телефоні (через додавання ярлика на головний екран).")