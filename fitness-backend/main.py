from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from database import get_db_connection
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
import os

app = FastAPI(title="Fitness Club API")

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# ПУТИ К ФАЙЛАМ
# ==========================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

print(f"📁 BASE_DIR: {BASE_DIR}")
print(f"📁 FRONTEND_DIR: {FRONTEND_DIR}")

# ==========================================
# SCHEMAS (Pydantic модели)
# ==========================================

class LoginRequest(BaseModel):
    username: str
    password: str

class SessionCreate(BaseModel):
    client_id: int
    coach_id: int
    duration_minutes: int
    session_type: str = "Силовая"
    note: Optional[str] = None

class SessionDetailCreate(BaseModel):
    exercise_id: int
    set_number: int
    reps: int
    weight_kg: float
    set_type: str = "рабочий"

class FeedbackCreate(BaseModel):
    feedback_text: str
    wellbeing_score: int

class MembershipCreate(BaseModel):
    name: str
    type: str
    duration_days: int
    price: float
    description: Optional[str] = None

class UserCreate(BaseModel):
    name: str
    email: str

class TrainerCreate(BaseModel):
    name: str
    email: str
    specialization: str

class PurchaseCreate(BaseModel):
    user_id: int
    membership_id: int
    price_paid: float
    coach_id: Optional[int] = None

class GoalCreate(BaseModel):
    exercise_id: Optional[int] = None
    exercise_name: Optional[str] = None
    goal_type: str
    target_value: float
    target_date: Optional[str] = None
    description: Optional[str] = None

class GoalUpdate(BaseModel):
    target_value: Optional[float] = None
    target_date: Optional[str] = None
    status: Optional[str] = None
    description: Optional[str] = None

class GoalProgressAdd(BaseModel):
    value: float
    progress_date: Optional[str] = None
    note: Optional[str] = None

class FinishSession(BaseModel):
    notes: Optional[str] = None

class CashierSessionCreate(BaseModel):
    user_id: int
    coach_id: Optional[int] = None
    duration_minutes: int = 60
    session_type: str = "Силовая"

class SessionResultCreate(BaseModel):
    exercise_name: str
    sets: List[dict]

# ==========================================
# АВТОРИЗАЦИЯ (ВХОД)
# ==========================================

@app.post("/api/v1/auth/login")
def login(request: LoginRequest):
    """Вход в систему по ФИО и ID"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id, name, email, role 
            FROM users 
            WHERE name = %s AND id = %s
        """, (request.username, int(request.password)))

        user = cursor.fetchone()

        if not user:
            raise HTTPException(
                status_code=401,
                detail="Неверное ФИО или ID. Проверьте правильность ввода."
            )

        # Проверяем роль и перенаправляем
        role_pages = {
            'admin': '/admin.html',
            'cashier': '/cashier.html',
            'trainer': '/coach.html',
            'client': '/client.html'
        }

        redirect_page = role_pages.get(user['role'], '/client.html')

        return {
            "status": "success",
            "message": f"Добро пожаловать, {user['name']}!",
            "user": {
                "id": user['id'],
                "name": user['name'],
                "email": user['email'],
                "role": user['role']
            },
            "redirect": redirect_page
        }
    except Exception as e:
        print(f"❌ Ошибка входа: {str(e)}")
        raise HTTPException(status_code=500, detail="Ошибка сервера")
    finally:
        cursor.close()
        conn.close()

# ==========================================
# ПУБЛИЧНЫЕ ЭНДПОИНТЫ
# ==========================================

@app.get("/api/v1/public/memberships")
def get_public_memberships():
    """Получить все абонементы для отображения на главной странице"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT 
                id,
                name,
                type,
                duration_days,
                price,
                description
            FROM memberships
            ORDER BY price ASC;
        """)

        result = cursor.fetchall()

        memberships = []
        for row in result:
            memberships.append({
                "id": row['id'],
                "name": row['name'],
                "type": row['type'] or "Стандартный",
                "duration_days": row['duration_days'],
                "price": float(row['price']),
                "description": row['description'] or ""
            })

        print(f"📦 Найдено абонементов: {len(memberships)}")
        return {"status": "success", "data": memberships}
    except Exception as e:
        print(f"❌ Ошибка получения абонементов: {str(e)}")
        return {"status": "error", "message": str(e), "data": []}
    finally:
        cursor.close()
        conn.close()

# ==========================================
# ВСЕ ОСТАЛЬНЫЕ ЭНДПОИНТЫ (АДМИН, КАССИР, ТРЕНЕР, КЛИЕНТ)
# ==========================================

# --- АДМИН ЭНДПОИНТЫ ---

@app.get("/api/v1/admin/stats")
def get_admin_stats():
    """Получить общую статистику"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT 
                COALESCE(SUM(price_paid), 0) as total_revenue
            FROM (
                SELECT price_paid FROM user_memberships
                UNION ALL
                SELECT price_paid FROM membership_purchases
            ) as all_purchases;
        """)
        revenue_res = cursor.fetchone()

        cursor.execute("""
            SELECT COUNT(*) as active_count 
            FROM user_memberships um
            JOIN users u ON um.user_id = u.id
            WHERE um.end_date > CURRENT_DATE
              AND NOT EXISTS (
                  SELECT 1 FROM coaches c WHERE c.user_id = u.id
              );
        """)
        active_res = cursor.fetchone()

        print(f"📊 Статистика: выручка={float(revenue_res['total_revenue'])} Br, активных={int(active_res['active_count'])}")

        return {
            "revenue": float(revenue_res['total_revenue']),
            "active_memberships": int(active_res['active_count']),
            "chart_labels": [],
            "chart_values": []
        }
    except Exception as e:
        print("Ошибка статистики:", str(e))
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.get("/api/v1/admin/memberships")
def get_all_memberships():
    """Получить все тарифы"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT 
                m.id, 
                m.name, 
                m.type, 
                m.duration_days,
                m.price, 
                m.description,
                COUNT(um.id) as active_count
            FROM memberships m
            LEFT JOIN user_memberships um ON um.membership_id = m.id AND um.end_date >= CURRENT_DATE
            GROUP BY m.id
            ORDER BY m.id DESC;
        """)
        result = cursor.fetchall()
        print("Загружено тарифов:", len(result))
        return result
    except Exception as e:
        print("Ошибка получения тарифов:", str(e))
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.post("/api/v1/admin/memberships")
def create_membership(membership: MembershipCreate):
    """Создать новый тариф"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO memberships (name, type, duration_days, price, description)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id;
        """, (membership.name, membership.type, membership.duration_days, membership.price, membership.description))

        result = cursor.fetchone()
        new_id = result['id']
        conn.commit()

        return {"status": "success", "message": "Абонемент успешно создан", "id": new_id}

    except Exception as e:
        conn.rollback()
        print("!!! ОШИБКА СОЗДАНИЯ АБОНЕМЕНТА !!!:", str(e))
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.delete("/api/v1/admin/memberships/{membership_id}")
def delete_membership(membership_id: int):
    """Удалить тариф"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, name FROM memberships WHERE id = %s;", (membership_id,))
        membership = cursor.fetchone()

        if not membership:
            raise HTTPException(status_code=404, detail="Тариф не найден")

        cursor.execute("""
            SELECT COUNT(*) as count 
            FROM user_memberships 
            WHERE membership_id = %s AND end_date >= CURRENT_DATE;
        """, (membership_id,))
        result = cursor.fetchone()
        active_count = result['count']

        if active_count > 0:
            cursor.execute("""
                UPDATE user_memberships 
                SET end_date = CURRENT_DATE - INTERVAL '1 day' 
                WHERE membership_id = %s AND end_date >= CURRENT_DATE;
            """, (membership_id,))
            print(f"⚠️ Деактивировано {active_count} абонементов с тарифом ID={membership_id}")

        cursor.execute("DELETE FROM memberships WHERE id = %s RETURNING id;", (membership_id,))
        deleted = cursor.fetchone()

        if not deleted:
            raise HTTPException(status_code=404, detail="Тариф не найден")

        conn.commit()
        print(f"✅ Удален тариф ID={membership_id} (и {active_count} абонементов деактивировано)")
        return {
            "status": "success",
            "message": f"Тариф успешно удален. Деактивировано абонементов: {active_count}"
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        conn.rollback()
        print(f"❌ Ошибка удаления тарифа: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.get("/api/v1/admin/trainers-count")
def get_trainers_count():
    """Получить количество тренеров"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) as count FROM coaches;")
        result = cursor.fetchone()
        return {"count": result['count']}
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
        return {"count": 0}
    finally:
        cursor.close()
        conn.close()

@app.get("/api/v1/admin/clients-count")
def get_clients_count():
    """Получить количество клиентов"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) as count FROM users;")
        result = cursor.fetchone()
        return {"count": result['count']}
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
        return {"count": 0}
    finally:
        cursor.close()
        conn.close()

@app.get("/api/v1/admin/trainers-list")
def get_trainers_list():
    """Получить список всех тренеров с количеством клиентов"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT 
                c.id as coach_id,
                u.id as user_id,
                u.name,
                u.email,
                c.specialization,
                COUNT(DISTINCT cc.client_id) as clients_count
            FROM coaches c
            JOIN users u ON c.user_id = u.id
            LEFT JOIN coach_clients cc ON c.id = cc.coach_id AND cc.is_active = true
            GROUP BY c.id, u.id, u.name, u.email, c.specialization
            ORDER BY u.name ASC;
        """)
        result = cursor.fetchall()
        return {"status": "success", "data": result}
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
        return {"status": "error", "message": str(e), "data": []}
    finally:
        cursor.close()
        conn.close()

@app.post("/api/v1/admin/trainers")
def create_trainer(trainer: TrainerCreate):
    """Зарегистрировать нового тренера"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM users WHERE email = %s;", (trainer.email,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Пользователь с таким Email уже существует")

        cursor.execute("""
            INSERT INTO users (name, email, role) 
            VALUES (%s, %s, 'trainer') 
            RETURNING id;
        """, (trainer.name, trainer.email))

        new_user_id = cursor.fetchone()['id']

        cursor.execute("""
            INSERT INTO coaches (user_id, specialization) 
            VALUES (%s, %s)
            RETURNING id;
        """, (new_user_id, trainer.specialization))

        new_coach_id = cursor.fetchone()['id']
        conn.commit()

        return {
            "status": "success",
            "message": f"Тренер {trainer.name} успешно зарегистрирован",
            "user_id": new_user_id,
            "coach_id": new_coach_id
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        conn.rollback()
        print("!!! ОШИБКА СОЗДАНИЯ ТРЕНЕРА !!!:", str(e))
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.get("/api/v1/admin/decline-requests")
def get_decline_requests():
    """Получить все запросы на отказ от клиентов"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT 
                dr.id as request_id,
                dr.coach_id,
                uc.name as coach_name,
                dr.client_id,
                ucl.name as client_name,
                ucl.email as client_email,
                dr.reason,
                dr.status,
                dr.created_at
            FROM coach_decline_requests dr
            JOIN users uc ON dr.coach_id = uc.id
            JOIN users ucl ON dr.client_id = ucl.id
            WHERE dr.status = 'pending'
            ORDER BY dr.created_at DESC;
        """)
        result = cursor.fetchall()
        return {"status": "success", "data": result}
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.post("/api/v1/admin/decline-requests/{request_id}/approve")
def approve_decline_request(request_id: int):
    """Администратор одобряет отказ от клиента"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT coach_id, client_id FROM coach_decline_requests 
            WHERE id = %s AND status = 'pending'
        """, (request_id,))

        request = cursor.fetchone()
        if not request:
            raise HTTPException(status_code=404, detail="Запрос не найден или уже обработан")

        coach_id = request['coach_id']
        client_id = request['client_id']

        cursor.execute("""
            UPDATE coach_clients 
            SET is_active = false 
            WHERE coach_id = %s AND client_id = %s AND is_active = true
        """, (coach_id, client_id))

        print(f"✅ Деактивирована связь тренер {coach_id} - клиент {client_id}")

        cursor.execute("""
            UPDATE coach_decline_requests 
            SET status = 'approved', 
                processed_at = CURRENT_TIMESTAMP,
                processed_by = 'admin'
            WHERE id = %s
            RETURNING id;
        """, (request_id,))

        conn.commit()
        return {"status": "success", "message": "Отказ от клиента одобрен. Клиент удален из списка тренера."}
    except Exception as e:
        conn.rollback()
        print(f"❌ Ошибка: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.post("/api/v1/admin/decline-requests/{request_id}/reject")
def reject_decline_request(request_id: int):
    """Администратор отклоняет отказ от клиента"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE coach_decline_requests 
            SET status = 'rejected', 
                processed_at = CURRENT_TIMESTAMP,
                processed_by = 'admin'
            WHERE id = %s AND status = 'pending'
            RETURNING id;
        """, (request_id,))

        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Запрос не найден или уже обработан")

        conn.commit()
        return {"status": "success", "message": "Отказ от клиента отклонен. Связь сохранена."}
    except Exception as e:
        conn.rollback()
        print(f"❌ Ошибка: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.get("/api/v1/admin/active-clients-list")
def get_active_clients_list():
    """Получить список клиентов с активными абонементами (без тренеров)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT 
                um.user_id,
                u.name as client_name,
                u.email as client_email,
                m.name as membership_name,
                TO_CHAR(um.end_date, 'DD.MM.YYYY') as end_date,
                (um.end_date - CURRENT_DATE) as days_left
            FROM user_memberships um
            JOIN users u ON um.user_id = u.id
            JOIN memberships m ON um.membership_id = m.id
            WHERE um.end_date > CURRENT_DATE
              AND u.id NOT IN (
                  SELECT user_id FROM coaches
              )
            ORDER BY u.name ASC;
        """)
        result = cursor.fetchall()
        return {"status": "success", "data": result}
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
        return {"status": "error", "message": str(e), "data": []}
    finally:
        cursor.close()
        conn.close()

@app.get("/api/v1/admin/chart-data")
def get_chart_data(period: str = "month"):
    """Получить данные для графика по периодам: day, month, year"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if period == "day":
            cursor.execute("""
                SELECT 
                    purchase_date as date,
                    COALESCE(SUM(price_paid), 0) as total
                FROM membership_purchases
                WHERE purchase_date >= CURRENT_DATE - INTERVAL '6 days'
                GROUP BY purchase_date
                UNION ALL
                SELECT 
                    start_date as date,
                    COALESCE(SUM(price_paid), 0) as total
                FROM user_memberships
                WHERE start_date >= CURRENT_DATE - INTERVAL '6 days'
                GROUP BY start_date
            """)
            result = cursor.fetchall()
            
            day_totals = {}
            for row in result:
                date_key = row['date'].strftime('%Y-%m-%d')
                if date_key in day_totals:
                    day_totals[date_key] += float(row['total'])
                else:
                    day_totals[date_key] = float(row['total'])
            
            days_map = {0: 'Вс', 1: 'Пн', 2: 'Вт', 3: 'Ср', 4: 'Чт', 5: 'Пт', 6: 'Сб'}
            full_week = []
            today = datetime.now().date()
            start_date = today - timedelta(days=6)
            
            for i in range(7):
                date = start_date + timedelta(days=i)
                date_key = date.strftime('%Y-%m-%d')
                full_week.append({
                    'label': date.strftime('%d.%m'),
                    'dow': date.weekday() + 1,
                    'total': day_totals.get(date_key, 0)
                })
            
            labels = [f"{day['label']} ({days_map[day['dow'] % 7]})" for day in full_week]
            values = [day['total'] for day in full_week]
            total = sum(values)
            
        elif period == "year":
            cursor.execute("""
                SELECT 
                    EXTRACT(YEAR FROM purchase_date) as year,
                    COALESCE(SUM(price_paid), 0) as total
                FROM membership_purchases
                GROUP BY EXTRACT(YEAR FROM purchase_date)
                UNION ALL
                SELECT 
                    EXTRACT(YEAR FROM start_date) as year,
                    COALESCE(SUM(price_paid), 0) as total
                FROM user_memberships
                GROUP BY EXTRACT(YEAR FROM start_date)
            """)
            result = cursor.fetchall()
            
            year_totals = {}
            for row in result:
                year = int(row['year'])
                if year in year_totals:
                    year_totals[year] += float(row['total'])
                else:
                    year_totals[year] = float(row['total'])
            
            sorted_years = sorted(year_totals.keys())
            labels = [str(year) for year in sorted_years]
            values = [year_totals[year] for year in sorted_years]
            total = sum(values)
            
        else:
            cursor.execute("""
                SELECT 
                    TO_CHAR(purchase_date, 'YYYY-MM') as month,
                    COALESCE(SUM(price_paid), 0) as total
                FROM membership_purchases
                WHERE purchase_date >= CURRENT_DATE - INTERVAL '11 months'
                GROUP BY TO_CHAR(purchase_date, 'YYYY-MM')
                UNION ALL
                SELECT 
                    TO_CHAR(start_date, 'YYYY-MM') as month,
                    COALESCE(SUM(price_paid), 0) as total
                FROM user_memberships
                WHERE start_date >= CURRENT_DATE - INTERVAL '11 months'
                GROUP BY TO_CHAR(start_date, 'YYYY-MM')
            """)
            result = cursor.fetchall()
            
            month_totals = {}
            for row in result:
                month_key = row['month']
                if month_key in month_totals:
                    month_totals[month_key] += float(row['total'])
                else:
                    month_totals[month_key] = float(row['total'])
            
            months_ru = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек']
            full_year = []
            today = datetime.now().date()
            
            for i in range(11, -1, -1):
                date = today.replace(day=1) - timedelta(days=i*30)
                month_num = date.month
                year = date.year
                month_key = f"{year}-{str(month_num).zfill(2)}"
                full_year.append({
                    'label': f"{months_ru[month_num-1]} {str(year)[-2:]}",
                    'month': month_num,
                    'year': year,
                    'total': month_totals.get(month_key, 0)
                })
            
            labels = [month['label'] for month in full_year]
            values = [month['total'] for month in full_year]
            total = sum(values)
        
        return {
            "status": "success",
            "labels": labels,
            "values": values,
            "total": total,
            "period_label": period,
            "period_range": f"Период: {period}"
        }
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}
    finally:
        cursor.close()
        conn.close()

# --- ТРЕНЕР ЭНДПОИНТЫ ---

@app.get("/api/v1/coach/by-user/{user_id}")
def get_coach_by_user_id(user_id: int):
    """Получить coach_id по user_id"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id as coach_id FROM coaches WHERE user_id = %s
        """, (user_id,))

        result = cursor.fetchone()
        if not result:
            return {
                "status": "error",
                "message": f"Тренер не найден для пользователя {user_id}",
                "coach_id": None
            }

        return {"status": "success", "coach_id": result['coach_id']}
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
        return {"status": "error", "message": str(e), "coach_id": None}
    finally:
        cursor.close()
        conn.close()

@app.get("/api/v1/coach/{coach_id}/profile")
def get_coach_profile(coach_id: int):
    """Получить информацию о тренере"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        print(f"🔍 Поиск тренера с ID: {coach_id}")

        cursor.execute("""
            SELECT 
                c.id as coach_id,
                u.id as user_id,
                u.name,
                u.email,
                c.specialization,
                COUNT(DISTINCT cc.client_id) as total_clients,
                COUNT(s.id) as total_sessions
            FROM coaches c
            JOIN users u ON c.user_id = u.id
            LEFT JOIN coach_clients cc ON c.id = cc.coach_id AND cc.is_active = true
            LEFT JOIN sessions s ON c.id = s.coach_id
            WHERE c.id = %s
            GROUP BY c.id, u.id, u.name, u.email, c.specialization;
        """, (coach_id,))

        result = cursor.fetchone()

        if not result:
            print(f"❌ Тренер с ID {coach_id} не найден")
            return {
                "status": "error",
                "message": f"Тренер с ID {coach_id} не найден",
                "data": {
                    "coach_id": coach_id,
                    "user_id": None,
                    "name": "Тренер не найден",
                    "email": "—",
                    "specialization": "—",
                    "total_clients": 0,
                    "total_sessions": 0
                }
            }

        return {"status": "success", "data": result}
    except Exception as e:
        print(f"❌ Ошибка получения профиля тренера: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "message": str(e),
            "data": None
        }
    finally:
        cursor.close()
        conn.close()

@app.get("/api/v1/coach/{coach_id}/membership")
def get_coach_membership(coach_id: int):
    """Получить абонемент тренера"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT user_id FROM coaches WHERE id = %s;", (coach_id,))
        coach = cursor.fetchone()
        if not coach:
            return {
                "status": "success",
                "has_membership": False,
                "message": "Тренер не найден"
            }

        user_id = coach['user_id']

        cursor.execute("""
            SELECT 
                m.name as membership_name,
                m.type as membership_type,
                m.price as membership_price,
                um.start_date,
                um.end_date,
                (um.end_date - CURRENT_DATE) as days_left,
                CASE 
                    WHEN um.end_date >= CURRENT_DATE THEN 'Активен'
                    ELSE 'Истек'
                END as status
            FROM user_memberships um
            JOIN memberships m ON um.membership_id = m.id
            WHERE um.user_id = %s 
            ORDER BY um.start_date DESC
            LIMIT 1;
        """, (user_id,))

        result = cursor.fetchone()

        if not result:
            return {
                "status": "success",
                "has_membership": False,
                "message": "Активных абонементов не найдено"
            }

        if result['days_left'] is not None:
            result['days_left'] = int(result['days_left'])

        return {
            "status": "success",
            "has_membership": True,
            "data": result
        }
    except Exception as e:
        print(f"❌ Ошибка получения абонемента тренера: {str(e)}")
        return {"status": "error", "message": str(e)}
    finally:
        cursor.close()
        conn.close()

@app.get("/api/v1/coach/{coach_id}/clients")
def get_coach_clients_list(coach_id: int):
    """Получить список клиентов тренера (только активные связи)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT 
                u.id as client_id,
                u.name as client_name,
                u.email as client_email,
                cc.assigned_date,
                (
                    SELECT COUNT(*) 
                    FROM sessions s 
                    WHERE s.user_id = u.id
                ) as total_sessions,
                (
                    SELECT m.name 
                    FROM user_memberships um
                    JOIN memberships m ON um.membership_id = m.id
                    WHERE um.user_id = u.id AND um.end_date >= CURRENT_DATE
                    LIMIT 1
                ) as membership_name,
                (
                    SELECT um.end_date
                    FROM user_memberships um
                    WHERE um.user_id = u.id AND um.end_date >= CURRENT_DATE
                    LIMIT 1
                ) as membership_end_date
            FROM coach_clients cc
            JOIN users u ON cc.client_id = u.id
            WHERE cc.coach_id = %s AND cc.is_active = true
            ORDER BY u.name ASC;
        """, (coach_id,))

        result = cursor.fetchall()
        print(f"✅ Найдено клиентов для тренера {coach_id}: {len(result)}")
        return {"status": "success", "data": result}
    except Exception as e:
        print(f"❌ Ошибка получения клиентов: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.get("/api/v1/coach/{coach_id}/active-sessions")
def get_active_sessions(coach_id: int):
    """Получить только активные тренировки (не завершенные)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        print(f"🔍 Поиск активных тренировок для тренера ID: {coach_id}")

        cursor.execute("""
            SELECT 
                s.id as session_id,
                s.user_id as client_id,
                u.name as client_name,
                s.session_datetime,
                s.duration_minutes,
                s.session_type,
                s.client_feedback,
                CASE 
                    WHEN s.client_feedback IS NOT NULL AND s.client_feedback != '' THEN 'completed'
                    WHEN (SELECT COUNT(*) FROM session_details WHERE session_id = s.id) = 0 THEN 'pending'
                    ELSE 'in_progress'
                END as status,
                (SELECT COUNT(*) FROM session_details WHERE session_id = s.id) as exercises_count
            FROM sessions s
            JOIN users u ON s.user_id = u.id
            WHERE s.coach_id = %s 
              AND s.is_coached = true
              AND (s.client_feedback IS NULL OR s.client_feedback = '')
            ORDER BY s.session_datetime DESC
            LIMIT 50;
        """, (coach_id,))

        result = cursor.fetchall()
        print(f"✅ Найдено активных тренировок: {len(result)}")

        data = []
        for row in result:
            data.append({
                'session_id': row['session_id'],
                'client_id': row['client_id'],
                'client_name': row['client_name'],
                'session_datetime': row['session_datetime'],
                'duration_minutes': row['duration_minutes'],
                'session_type': row['session_type'],
                'status': row['status'],
                'exercises_count': row['exercises_count']
            })

        return {"status": "success", "data": data}
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e), "data": []}
    finally:
        cursor.close()
        conn.close()

@app.post("/api/v1/coach/sessions/{session_id}/start")
def start_session(session_id: int, exercises: List[dict]):
    """Сохранить упражнения и подходы в тренировку"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        print("=" * 70)
        print("🔵 СОХРАНЕНИЕ УПРАЖНЕНИЙ В ТРЕНИРОВКУ")
        print(f"🔵 session_id: {session_id}")
        print(f"🔵 Получено упражнений: {len(exercises)}")
        print("=" * 70)

        cursor.execute("SELECT id, client_feedback FROM sessions WHERE id = %s;", (session_id,))
        session = cursor.fetchone()
        if not session:
            print("❌ Тренировка не найдена!")
            return {"status": "error", "message": "Тренировка не найдена"}

        if session['client_feedback'] is not None and session['client_feedback'] != '':
            print("❌ Тренировка уже завершена!")
            return {"status": "error", "message": "Тренировка уже завершена!"}

        cursor.execute("DELETE FROM session_details WHERE session_id = %s;", (session_id,))
        print(f"🔵 Удалены старые детали для session_id {session_id}")

        added_count = 0

        for idx, exercise_data in enumerate(exercises):
            exercise_name = exercise_data.get('name', '').strip()
            sets = exercise_data.get('sets', [])

            print(f"🔵 Упражнение {idx+1}: '{exercise_name}', подходов: {len(sets)}")

            if not exercise_name or not sets:
                continue

            cursor.execute("SELECT id FROM exercises WHERE name ILIKE %s LIMIT 1;", (f"%{exercise_name}%",))
            exercise = cursor.fetchone()

            if not exercise:
                cursor.execute("INSERT INTO exercises (name) VALUES (%s) RETURNING id;", (exercise_name,))
                exercise_id = cursor.fetchone()['id']
                print(f"🔵 Создано новое упражнение: {exercise_name} (ID: {exercise_id})")
            else:
                exercise_id = exercise['id']
                print(f"🔵 Найдено упражнение: {exercise_name} (ID: {exercise_id})")

            for set_data in sets:
                set_number = set_data.get('set_number', 1)
                reps = set_data.get('reps', 0)
                weight = set_data.get('weight', 0)

                print(f"🔵   Подход {set_number}: {reps} повторений, {weight} кг")

                cursor.execute("""
                    INSERT INTO session_details (session_id, exercise_id, set_number, reps, weight_kg, set_type)
                    VALUES (%s, %s, %s, %s, %s, 'рабочий');
                """, (session_id, exercise_id, set_number, reps, weight))
                added_count += 1

        conn.commit()
        print(f"✅ СОХРАНЕНО {added_count} ПОДХОДОВ!")
        print("=" * 70)

        return {
            "status": "success",
            "message": f"Сохранено {added_count} подходов",
            "added_count": added_count
        }
    except Exception as e:
        conn.rollback()
        print(f"❌ ОШИБКА: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}
    finally:
        cursor.close()
        conn.close()

@app.get("/api/v1/coach/sessions/{session_id}/details")
def get_session_details(session_id: int):
    """Получить детали тренировки (упражнения и подходы)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT 
                sd.id,
                e.name as exercise_name,
                sd.set_number,
                sd.reps,
                sd.weight_kg
            FROM session_details sd
            JOIN exercises e ON sd.exercise_id = e.id
            WHERE sd.session_id = %s
            ORDER BY sd.id;
        """, (session_id,))

        result = cursor.fetchall()
        return {"status": "success", "data": result}
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
        return {"status": "error", "message": str(e)}
    finally:
        cursor.close()
        conn.close()

@app.post("/api/v1/coach/sessions/{session_id}/finish")
def finish_session(session_id: int, data: dict = None):
    """Завершить тренировку"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        print("=" * 70)
        print("🏁 ЗАВЕРШЕНИЕ ТРЕНИРОВКИ")
        print(f"🏁 session_id: {session_id}")
        print("=" * 70)

        cursor.execute("SELECT id, client_feedback FROM sessions WHERE id = %s;", (session_id,))
        session = cursor.fetchone()
        if not session:
            print("❌ Тренировка не найдена!")
            return {"status": "error", "message": "Тренировка не найдена"}

        if session['client_feedback'] is not None and session['client_feedback'] != '':
            print("❌ Тренировка уже завершена!")
            return {"status": "error", "message": "Тренировка уже завершена!"}

        cursor.execute("SELECT COUNT(*) as count FROM session_details WHERE session_id = %s;", (session_id,))
        count = cursor.fetchone()
        print(f"🏁 Найдено упражнений: {count['count']}")

        if count['count'] == 0:
            print("⚠️ Нет упражнений для завершения!")
            return {"status": "error", "message": "Нет упражнений для завершения тренировки!"}

        notes = "Тренировка завершена"
        if data and data.get('notes'):
            notes = data['notes']
            print(f"🏁 Заметки: {notes}")

        cursor.execute("""
            UPDATE sessions 
            SET client_feedback = %s
            WHERE id = %s
            RETURNING id;
        """, (notes, session_id))

        if not cursor.fetchone():
            print("❌ Не удалось обновить тренировку!")
            return {"status": "error", "message": "Не удалось завершить тренировку"}

        conn.commit()
        print(f"✅ Тренировка {session_id} ЗАВЕРШЕНА!")
        print(f"✅ Сохранено {count['count']} упражнений")
        print("=" * 70)

        return {
            "status": "success",
            "message": f"Тренировка завершена! Сохранено {count['count']} упражнений.",
            "exercises_count": count['count']
        }
    except Exception as e:
        conn.rollback()
        print(f"❌ ОШИБКА: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}
    finally:
        cursor.close()
        conn.close()

@app.get("/api/v1/coach/clients/{client_id}/info")
def get_client_info_for_coach(client_id: int):
    """Получить полную информацию о клиенте"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT 
                u.id,
                u.name,
                u.email,
                (
                    SELECT m.name 
                    FROM user_memberships um
                    JOIN memberships m ON um.membership_id = m.id
                    WHERE um.user_id = u.id AND um.end_date >= CURRENT_DATE
                    LIMIT 1
                ) as membership_name,
                (
                    SELECT um.end_date
                    FROM user_memberships um
                    WHERE um.user_id = u.id AND um.end_date >= CURRENT_DATE
                    LIMIT 1
                ) as membership_end_date,
                (
                    SELECT COUNT(*) 
                    FROM sessions s 
                    WHERE s.user_id = u.id
                ) as total_sessions
            FROM users u
            WHERE u.id = %s;
        """, (client_id,))

        client = cursor.fetchone()
        if not client:
            raise HTTPException(status_code=404, detail="Клиент не найден")

        return {"status": "success", "data": client}
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.get("/api/v1/coach/clients/{client_id}/progress")
def get_client_progress_for_coach(client_id: int, exercise_name: Optional[str] = None):
    """Получить прогресс клиента по упражнениям"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        print(f"🔍 Поиск прогресса для клиента user_id: {client_id}, упражнение: {exercise_name or 'все'}")

        cursor.execute("""
            SELECT DISTINCT e.name
            FROM session_details sd
            JOIN sessions s ON sd.session_id = s.id
            JOIN exercises e ON sd.exercise_id = e.id
            WHERE s.user_id = %s
            ORDER BY e.name;
        """, (client_id,))
        exercises = cursor.fetchall()
        available_exercises = [ex['name'] for ex in exercises]

        if not available_exercises:
            return {
                "status": "success",
                "has_data": False,
                "available_exercises": [],
                "message": "Нет данных о тренировках"
            }

        if not exercise_name:
            exercise_name = available_exercises[0]

        cursor.execute("""
            SELECT 
                s.session_datetime::date as date,
                s.id as session_id,
                MAX(sd.weight_kg) as max_weight,
                MAX(sd.reps) as max_reps,
                COUNT(sd.id) as total_sets
            FROM session_details sd
            JOIN sessions s ON sd.session_id = s.id
            JOIN exercises e ON sd.exercise_id = e.id
            WHERE s.user_id = %s 
              AND e.name = %s
            GROUP BY s.session_datetime::date, s.id
            ORDER BY s.session_datetime::date ASC;
        """, (client_id, exercise_name))

        result = cursor.fetchall()

        data = []
        for row in result:
            data.append({
                'date': row['date'],
                'max_weight': float(row['max_weight'] or 0),
                'max_reps': int(row['max_reps'] or 0),
                'total_sets': int(row['total_sets'] or 0),
                'session_id': row['session_id']
            })

        print(f"✅ Найдено записей: {len(data)}")

        return {
            "status": "success",
            "has_data": len(data) > 0,
            "current_exercise": exercise_name,
            "available_exercises": available_exercises,
            "data": data
        }

    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "has_data": False,
            "message": str(e),
            "available_exercises": [],
            "data": []
        }
    finally:
        cursor.close()
        conn.close()

@app.post("/api/v1/coach/decline-client/{client_id}")
def decline_client(client_id: int, data: dict):
    """Тренер отказывается от клиента"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        coach_id = data.get('coach_id')
        reason = data.get('reason', '')

        if not coach_id:
            raise HTTPException(status_code=400, detail="coach_id обязателен")

        cursor.execute("""
            SELECT id FROM coach_clients 
            WHERE coach_id = %s AND client_id = %s AND is_active = true
        """, (coach_id, client_id))

        relation = cursor.fetchone()
        if not relation:
            raise HTTPException(status_code=404, detail="Активная связь тренер-клиент не найдена")

        cursor.execute("""
            SELECT id FROM coach_decline_requests 
            WHERE coach_id = %s AND client_id = %s AND status = 'pending'
        """, (coach_id, client_id))

        existing = cursor.fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="Запрос на отказ уже отправлен")

        cursor.execute("""
            INSERT INTO coach_decline_requests (
                coach_id, 
                client_id, 
                reason, 
                status, 
                created_at
            )
            VALUES (%s, %s, %s, 'pending', CURRENT_TIMESTAMP)
            RETURNING id;
        """, (coach_id, client_id, reason))

        request_id = cursor.fetchone()['id']
        conn.commit()

        return {
            "status": "success",
            "message": "Запрос на отказ от клиента отправлен администратору",
            "request_id": request_id
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        conn.rollback()
        print(f"❌ Ошибка: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.get("/api/v1/coach/{coach_id}/progress")
def get_coach_progress(coach_id: int, exercise_name: Optional[str] = None):
    """Получить прогресс тренера по упражнениям"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT user_id FROM coaches WHERE id = %s;", (coach_id,))
        coach = cursor.fetchone()
        if not coach:
            return {
                "status": "success",
                "has_data": False,
                "message": "Тренер не найден",
                "available_exercises": [],
                "data": []
            }

        user_id = coach['user_id']
        print(f"🔍 Поиск прогресса для тренера user_id: {user_id}, упражнение: {exercise_name or 'все'}")

        cursor.execute("""
            SELECT DISTINCT e.name
            FROM session_details sd
            JOIN sessions s ON sd.session_id = s.id
            JOIN exercises e ON sd.exercise_id = e.id
            WHERE s.user_id = %s
            ORDER BY e.name;
        """, (user_id,))
        exercises = cursor.fetchall()
        available_exercises = [ex['name'] for ex in exercises]

        if not available_exercises:
            return {
                "status": "success",
                "has_data": False,
                "available_exercises": [],
                "message": "Нет данных о тренировках тренера"
            }

        if not exercise_name:
            exercise_name = available_exercises[0]

        cursor.execute("""
            SELECT 
                s.session_datetime::date as date,
                s.id as session_id,
                MAX(sd.weight_kg) as max_weight,
                MAX(sd.reps) as max_reps,
                COUNT(sd.id) as total_sets
            FROM session_details sd
            JOIN sessions s ON sd.session_id = s.id
            JOIN exercises e ON sd.exercise_id = e.id
            WHERE s.user_id = %s 
              AND e.name = %s
            GROUP BY s.session_datetime::date, s.id
            ORDER BY s.session_datetime::date ASC;
        """, (user_id, exercise_name))

        result = cursor.fetchall()

        data = []
        for row in result:
            data.append({
                'date': row['date'],
                'max_weight': float(row['max_weight'] or 0),
                'max_reps': int(row['max_reps'] or 0),
                'total_sets': int(row['total_sets'] or 0),
                'session_id': row['session_id']
            })

        print(f"✅ Найдено записей: {len(data)}")

        return {
            "status": "success",
            "has_data": len(data) > 0,
            "current_exercise": exercise_name,
            "available_exercises": available_exercises,
            "data": data
        }

    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "has_data": False,
            "message": str(e),
            "available_exercises": [],
            "data": []
        }
    finally:
        cursor.close()
        conn.close()

# --- КЛИЕНТ ЭНДПОИНТЫ ---

@app.get("/api/v1/client/{client_id}/membership")
def get_client_membership(client_id: int):
    """Получить информацию об абонементе клиента"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT 
                m.name as membership_name,
                m.type as membership_type,
                m.price as membership_price,
                um.start_date,
                um.end_date,
                (um.end_date - CURRENT_DATE) as days_left,
                CASE 
                    WHEN um.end_date >= CURRENT_DATE THEN 'Активен'
                    ELSE 'Истек'
                END as status
            FROM user_memberships um
            JOIN memberships m ON um.membership_id = m.id
            WHERE um.user_id = %s 
            ORDER BY um.start_date DESC
            LIMIT 1;
        """, (client_id,))

        result = cursor.fetchone()

        if not result:
            return {
                "status": "success",
                "has_membership": False,
                "message": "Активных абонементов не найдено"
            }

        if result['days_left'] is not None:
            result['days_left'] = int(result['days_left'])

        return {
            "status": "success",
            "has_membership": True,
            "data": result
        }
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.get("/api/v1/client/{client_id}/trainer")
def get_client_trainer(client_id: int):
    """Получить информацию о тренере клиента"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT 
                u.id as trainer_id,
                u.name as trainer_name,
                u.email as trainer_email,
                c.specialization,
                COALESCE((
                    SELECT COUNT(*) 
                    FROM sessions s 
                    WHERE s.coach_id = c.id AND s.user_id = %s
                ), 0) as total_sessions
            FROM coach_clients cc
            JOIN coaches c ON cc.coach_id = c.id
            JOIN users u ON c.user_id = u.id
            WHERE cc.client_id = %s AND cc.is_active = true
            ORDER BY cc.assigned_date DESC
            LIMIT 1;
        """, (client_id, client_id))

        result = cursor.fetchone()

        if not result:
            cursor.execute("""
                SELECT 
                    u.id as trainer_id,
                    u.name as trainer_name,
                    u.email as trainer_email,
                    c.specialization,
                    COUNT(s.id) as total_sessions
                FROM sessions s
                JOIN coaches c ON s.coach_id = c.id
                JOIN users u ON c.user_id = u.id
                WHERE s.user_id = %s
                GROUP BY u.id, u.name, u.email, c.specialization
                ORDER BY s.session_datetime DESC
                LIMIT 1;
            """, (client_id,))
            result = cursor.fetchone()

        if not result:
            return {
                "status": "success",
                "has_trainer": False,
                "message": "Тренер не назначен"
            }

        return {
            "status": "success",
            "has_trainer": True,
            "data": result
        }

    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
        return {
            "status": "success",
            "has_trainer": False,
            "message": "Ошибка загрузки тренера"
        }
    finally:
        cursor.close()
        conn.close()

@app.get("/api/v1/client/{client_id}/progress")
def get_client_progress(client_id: int, exercise_name: Optional[str] = None):
    """Прогресс клиента в упражнениях"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        print(f"🔍 Поиск прогресса для клиента ID: {client_id}, упражнение: {exercise_name or 'все'}")

        cursor.execute("""
            SELECT DISTINCT e.name
            FROM session_details sd
            JOIN sessions s ON sd.session_id = s.id
            JOIN exercises e ON sd.exercise_id = e.id
            WHERE s.user_id = %s
            ORDER BY e.name;
        """, (client_id,))
        exercises = cursor.fetchall()
        available_exercises = [ex['name'] for ex in exercises]

        print(f"📋 Доступные упражнения: {available_exercises}")

        if not available_exercises:
            return {
                "status": "success",
                "has_data": False,
                "available_exercises": [],
                "message": "Нет данных о тренировках"
            }

        if not exercise_name:
            exercise_name = available_exercises[0]
            print(f"📋 Выбрано первое упражнение: {exercise_name}")

        cursor.execute("""
            SELECT 
                s.session_datetime::date as date,
                s.id as session_id,
                MAX(sd.weight_kg) as max_weight,
                MAX(sd.reps) as max_reps,
                COUNT(sd.id) as total_sets
            FROM session_details sd
            JOIN sessions s ON sd.session_id = s.id
            JOIN exercises e ON sd.exercise_id = e.id
            WHERE s.user_id = %s 
              AND e.name = %s
            GROUP BY s.session_datetime::date, s.id
            ORDER BY s.session_datetime::date ASC;
        """, (client_id, exercise_name))

        result = cursor.fetchall()
        print(f"✅ Найдено записей: {len(result)}")

        data = []
        for row in result:
            data.append({
                'date': row['date'],
                'max_weight': float(row['max_weight'] or 0),
                'max_reps': int(row['max_reps'] or 0),
                'total_sets': int(row['total_sets'] or 0),
                'session_id': row['session_id']
            })

        return {
            "status": "success",
            "has_data": len(data) > 0,
            "current_exercise": exercise_name,
            "available_exercises": available_exercises,
            "data": data
        }

    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "has_data": False,
            "message": str(e),
            "available_exercises": [],
            "data": []
        }
    finally:
        cursor.close()
        conn.close()

@app.get("/api/v1/client/{client_id}/recent-sessions")
def get_recent_sessions(client_id: int, limit: int = 5):
    """Получить последние тренировки клиента"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT 
                s.id,
                s.session_datetime,
                s.duration_minutes,
                s.session_type,
                u.name as coach_name,
                s.client_feedback,
                s.wellbeing_score,
                COUNT(sd.id) as exercises_count
            FROM sessions s
            LEFT JOIN coaches c ON s.coach_id = c.id
            LEFT JOIN users u ON c.user_id = u.id
            LEFT JOIN session_details sd ON s.id = sd.session_id
            WHERE s.user_id = %s
            GROUP BY s.id, u.name
            ORDER BY s.session_datetime DESC
            LIMIT %s;
        """, (client_id, limit))

        result = cursor.fetchall()
        return {
            "status": "success",
            "data": result
        }
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.get("/api/v1/client/{client_id}/sessions")
def get_client_sessions(client_id: int):
    """Получить все тренировки клиента"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT 
                s.id AS session_id,
                s.session_datetime,
                s.session_type,
                s.duration_minutes,
                u.name AS coach_name,
                s.is_coached,
                s.client_feedback,
                s.wellbeing_score
            FROM sessions s
            LEFT JOIN coaches c ON s.coach_id = c.id
            LEFT JOIN users u ON c.user_id = u.id
            WHERE s.user_id = %s
            ORDER BY s.session_datetime DESC;
        """, (client_id,))
        result = cursor.fetchall()
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.patch("/api/v1/client/sessions/{session_id}/feedback")
def leave_feedback(session_id: int, feedback: FeedbackCreate):
    """Оставить отзыв на тренировку"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, user_id FROM sessions WHERE id = %s;", (session_id,))
        session = cursor.fetchone()
        if not session:
            raise HTTPException(status_code=404, detail="Тренировка не найдена")

        cursor.execute("""
            UPDATE sessions
            SET client_feedback = %s, wellbeing_score = %s
            WHERE id = %s
            RETURNING id;
        """, (feedback.feedback_text, feedback.wellbeing_score, session_id))

        conn.commit()
        return {
            "status": "success",
            "message": "Спасибо за отзыв!",
            "session_id": session_id
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        conn.rollback()
        print(f"❌ Ошибка: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

# --- ЦЕЛИ КЛИЕНТА ---

@app.get("/api/v1/client/{client_id}/goals")
def get_client_goals(client_id: int):
    """Получить все цели клиента"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT 
                g.id,
                g.user_id,
                g.exercise_id,
                e.name as exercise_name,
                g.goal_type,
                g.target_value,
                g.current_value,
                g.start_date,
                g.target_date,
                g.status,
                g.description,
                g.created_at,
                (SELECT value FROM goal_progress 
                 WHERE goal_id = g.id 
                 ORDER BY progress_date DESC 
                 LIMIT 1) as last_progress_value,
                (SELECT progress_date FROM goal_progress 
                 WHERE goal_id = g.id 
                 ORDER BY progress_date DESC 
                 LIMIT 1) as last_progress_date,
                CASE 
                    WHEN g.status = 'achieved' THEN 'Достигнута ✅'
                    WHEN g.status = 'active' AND g.current_value >= g.target_value THEN 'Достигнута ✅'
                    WHEN g.status = 'active' THEN 'В процессе 🏃'
                    WHEN g.status = 'failed' THEN 'Не выполнена ❌'
                    WHEN g.status = 'cancelled' THEN 'Отменена ⛔'
                    ELSE g.status
                END as status_display
            FROM client_goals g
            LEFT JOIN exercises e ON g.exercise_id = e.id
            WHERE g.user_id = %s
            ORDER BY 
                CASE g.status 
                    WHEN 'active' THEN 1
                    WHEN 'achieved' THEN 2
                    ELSE 3
                END,
                g.created_at DESC;
        """, (client_id,))

        result = cursor.fetchall()
        return {"status": "success", "data": result}

    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.post("/api/v1/client/{client_id}/goals")
def create_goal(client_id: int, goal: GoalCreate):
    """Создать новую цель"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM users WHERE id = %s;", (client_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Клиент не найден")

        exercise_id = goal.exercise_id
        if not exercise_id and goal.exercise_name:
            cursor.execute(
                "SELECT id FROM exercises WHERE name ILIKE %s LIMIT 1;",
                (f"%{goal.exercise_name}%",)
            )
            exercise = cursor.fetchone()
            if exercise:
                exercise_id = exercise['id']
            else:
                cursor.execute(
                    "INSERT INTO exercises (name) VALUES (%s) RETURNING id;",
                    (goal.exercise_name,)
                )
                exercise_id = cursor.fetchone()['id']

        cursor.execute("""
            INSERT INTO client_goals (
                user_id, exercise_id, goal_type, target_value, 
                target_date, description, status
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'active')
            RETURNING id;
        """, (
            client_id,
            exercise_id,
            goal.goal_type,
            goal.target_value,
            goal.target_date,
            goal.description
        ))

        goal_id = cursor.fetchone()['id']
        conn.commit()

        return {
            "status": "success",
            "message": "Цель успешно создана!",
            "goal_id": goal_id
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        conn.rollback()
        print(f"❌ Ошибка: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.post("/api/v1/client/goals/{goal_id}/progress")
def add_goal_progress(goal_id: int, progress: GoalProgressAdd):
    """Добавить прогресс к цели"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id, user_id, target_value, current_value 
            FROM client_goals 
            WHERE id = %s AND status = 'active';
        """, (goal_id,))

        goal = cursor.fetchone()
        if not goal:
            raise HTTPException(status_code=404, detail="Цель не найдена или неактивна")

        progress_date = progress.progress_date or datetime.now().date().isoformat()

        cursor.execute("""
            INSERT INTO goal_progress (goal_id, value, progress_date, note)
            VALUES (%s, %s, %s, %s)
            RETURNING id;
        """, (goal_id, progress.value, progress_date, progress.note))

        progress_id = cursor.fetchone()['id']

        new_current = max(goal['current_value'] or 0, progress.value)
        cursor.execute("""
            UPDATE client_goals 
            SET current_value = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s;
        """, (new_current, goal_id))

        if new_current >= goal['target_value']:
            cursor.execute("""
                UPDATE client_goals 
                SET status = 'achieved', updated_at = CURRENT_TIMESTAMP
                WHERE id = %s;
            """, (goal_id,))

        conn.commit()

        return {
            "status": "success",
            "message": "Прогресс добавлен!",
            "progress_id": progress_id,
            "current_value": new_current,
            "target_value": goal['target_value'],
            "is_achieved": new_current >= goal['target_value']
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        conn.rollback()
        print(f"❌ Ошибка: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.delete("/api/v1/client/goals/{goal_id}")
def delete_goal(goal_id: int):
    """Удалить цель"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM goal_progress WHERE goal_id = %s;", (goal_id,))
        cursor.execute("DELETE FROM client_goals WHERE id = %s RETURNING id;", (goal_id,))

        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Цель не найдена")

        conn.commit()
        return {"status": "success", "message": "Цель удалена"}

    except HTTPException as he:
        raise he
    except Exception as e:
        conn.rollback()
        print(f"❌ Ошибка: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

# --- КАССИР ЭНДПОИНТЫ ---

@app.get("/api/v1/cashier/users")
def get_all_users_for_cashier():
    """Получить список пользователей"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id, name, email 
            FROM users 
            WHERE id NOT IN (
                SELECT user_id FROM coaches
            )
            ORDER BY name ASC;
        """)
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

@app.get("/api/v1/cashier/memberships")
def get_all_memberships_for_cashier():
    """Получить список тарифов"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, name, price FROM memberships ORDER BY price ASC;")
        res = cursor.fetchall()
        print("ОТВЕТ БАЗЫ ПО ТАРИФАМ:", res)
        return res
    except Exception as e:
        print("!!! ОШИБКА ПОЛУЧЕНИЯ ТАРИФОВ !!!:", str(e))
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.get("/api/v1/cashier/coaches")
def get_coaches_for_cashier():
    """Получить список тренеров"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT 
                c.id as coach_id,
                u.name as coach_name,
                c.specialization,
                COUNT(s.id) as sessions_count
            FROM coaches c
            JOIN users u ON c.user_id = u.id
            LEFT JOIN sessions s ON c.id = s.coach_id
            WHERE c.is_active = true OR c.is_active IS NULL
            GROUP BY c.id, u.name, c.specialization
            ORDER BY u.name ASC;
        """)
        result = cursor.fetchall()
        return result
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
        return []
    finally:
        cursor.close()
        conn.close()

@app.post("/api/v1/cashier/users")
def cashier_create_user(user: UserCreate):
    """Создать нового клиента"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM users WHERE email = %s;", (user.email,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Пользователь с таким Email уже существует")

        cursor.execute("""
            INSERT INTO users (name, email) 
            VALUES (%s, %s) 
            RETURNING id;
        """, (user.name, user.email))

        new_id = cursor.fetchone()['id']
        conn.commit()
        return {"status": "success", "message": "Клиент успешно зарегистрирован", "id": new_id}

    except HTTPException as he:
        raise he
    except Exception as e:
        conn.rollback()
        print("!!! ОШИБКА СОЗДАНИЯ КЛИЕНТА !!!:", str(e))
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.post("/api/v1/cashier/purchases")
def create_purchase(purchase: PurchaseCreate):
    """Оформить продажу абонемента"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT duration_days, price FROM memberships WHERE id = %s;", (purchase.membership_id,))
        membership = cursor.fetchone()

        if not membership:
            raise HTTPException(status_code=404, detail="Тариф не найден")

        duration_days = membership['duration_days']
        start_date = datetime.now().date()
        end_date = start_date + timedelta(days=duration_days)

        cursor.execute("""
            SELECT id FROM user_memberships 
            WHERE user_id = %s AND end_date >= CURRENT_DATE
        """, (purchase.user_id,))

        existing = cursor.fetchone()
        if existing:
            cursor.execute("""
                UPDATE user_memberships 
                SET end_date = CURRENT_DATE - INTERVAL '1 day' 
                WHERE id = %s;
            """, (existing['id'],))

        cursor.execute("""
            INSERT INTO user_memberships (user_id, membership_id, start_date, end_date, price_paid)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id;
        """, (purchase.user_id, purchase.membership_id, start_date, end_date, purchase.price_paid))

        new_id = cursor.fetchone()['id']

        if purchase.coach_id:
            # ===== ПРОВЕРКА НА 30 КЛИЕНТОВ =====
            cursor.execute("""
                SELECT COUNT(*) as count 
                FROM coach_clients 
                WHERE coach_id = %s AND is_active = true
            """, (purchase.coach_id,))
            result = cursor.fetchone()
            current_clients = result['count'] if result else 0
            
            if current_clients >= 30:
                raise HTTPException(
                    status_code=400, 
                    detail=f"У тренера уже максимальное количество клиентов (30). Невозможно назначить нового клиента."
                )
            
            cursor.execute("""
                UPDATE coach_clients 
                SET is_active = false 
                WHERE client_id = %s;
            """, (purchase.user_id,))

            cursor.execute("""
                SELECT id FROM coach_clients 
                WHERE coach_id = %s AND client_id = %s
            """, (purchase.coach_id, purchase.user_id))

            existing_relation = cursor.fetchone()

            if existing_relation:
                cursor.execute("""
                    UPDATE coach_clients 
                    SET is_active = true, assigned_date = CURRENT_DATE
                    WHERE id = %s;
                """, (existing_relation['id'],))
                print(f"✅ Реактивирована связь тренер ID={purchase.coach_id} - клиент ID={purchase.user_id}")
            else:
                cursor.execute("""
                    INSERT INTO coach_clients (coach_id, client_id, assigned_date, is_active)
                    VALUES (%s, %s, CURRENT_DATE, true)
                    RETURNING id;
                """, (purchase.coach_id, purchase.user_id))
                print(f"✅ Создана новая связь тренер ID={purchase.coach_id} - клиент ID={purchase.user_id}")

        conn.commit()

        return {
            "status": "success",
            "message": "Абонемент успешно активирован!",
            "purchase_id": new_id,
            "coach_assigned": bool(purchase.coach_id)
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        conn.rollback()
        print("Ошибка при покупке:", str(e))
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.get("/api/v1/cashier/active-clients")
def get_active_clients(user_type: str = "all"):
    """Получить клиентов с активными абонементами"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if user_type == "trainers":
            cursor.execute("""
                SELECT 
                    um.user_id,
                    u.name as client_name,
                    u.email as client_email,
                    m.name as membership_name,
                    TO_CHAR(um.end_date, 'DD.MM.YYYY') as end_date
                FROM user_memberships um
                JOIN users u ON um.user_id = u.id
                JOIN memberships m ON um.membership_id = m.id
                WHERE um.end_date > CURRENT_DATE
                  AND u.id IN (
                      SELECT user_id FROM coaches
                  )
                ORDER BY u.name ASC;
            """)
        elif user_type == "clients":
            cursor.execute("""
                SELECT 
                    um.user_id,
                    u.name as client_name,
                    u.email as client_email,
                    m.name as membership_name,
                    TO_CHAR(um.end_date, 'DD.MM.YYYY') as end_date
                FROM user_memberships um
                JOIN users u ON um.user_id = u.id
                JOIN memberships m ON um.membership_id = m.id
                WHERE um.end_date > CURRENT_DATE
                  AND u.id NOT IN (
                      SELECT user_id FROM coaches
                  )
                ORDER BY u.name ASC;
            """)
        else:
            cursor.execute("""
                SELECT 
                    um.user_id,
                    u.name as client_name,
                    u.email as client_email,
                    m.name as membership_name,
                    TO_CHAR(um.end_date, 'DD.MM.YYYY') as end_date
                FROM user_memberships um
                JOIN users u ON um.user_id = u.id
                JOIN memberships m ON um.membership_id = m.id
                WHERE um.end_date > CURRENT_DATE
                ORDER BY u.name ASC;
            """)

        return cursor.fetchall()
    except Exception as e:
        print(f"Ошибка: {str(e)}")
        import traceback
        traceback.print_exc()
        return []
    finally:
        cursor.close()
        conn.close()

@app.post("/api/v1/cashier/create-session")
def create_session_by_cashier(session: CashierSessionCreate):
    """Создать тренировку при пропуске клиента"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        print(f"🔵 Создание тренировки для пользователя {session.user_id}")

        coach_id = session.coach_id
        if not coach_id:
            cursor.execute("""
                SELECT coach_id 
                FROM coach_clients 
                WHERE client_id = %s AND is_active = true
                ORDER BY assigned_date DESC
                LIMIT 1;
            """, (session.user_id,))
            coach = cursor.fetchone()
            if coach:
                coach_id = coach['coach_id']
                print(f"👤 Найден тренер клиента: {coach_id}")

        if not coach_id:
            cursor.execute("SELECT id FROM coaches LIMIT 1;")
            coach = cursor.fetchone()
            if coach:
                coach_id = coach['id']
                print(f"👤 Взят первый тренер: {coach_id}")

        if not coach_id:
            raise HTTPException(status_code=400, detail="Нет тренеров в системе")

        print(f"✅ Тренер ID: {coach_id}")

        cursor.execute("""
            INSERT INTO sessions (user_id, coach_id, session_datetime, duration_minutes, session_type, is_coached)
            VALUES (%s, %s, CURRENT_TIMESTAMP, %s, %s, true)
            RETURNING id;
        """, (session.user_id, coach_id, session.duration_minutes, session.session_type))

        session_id = cursor.fetchone()['id']
        conn.commit()

        print(f"✅ Тренировка создана! ID: {session_id}, coach_id: {coach_id}")

        return {
            "status": "success",
            "message": f"Тренировка создана!",
            "session_id": session_id,
            "coach_id": coach_id
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        conn.rollback()
        print(f"❌ Ошибка: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.post("/api/v1/cashier/log-pass")
def log_client_pass(pass_data: dict):
    """Сохранить запись о пропуске клиента"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        user_id = pass_data.get('user_id')
        client_name = pass_data.get('client_name')

        if not user_id:
            raise HTTPException(status_code=400, detail="user_id обязателен")

        cursor.execute("""
            INSERT INTO visits (user_id, visit_datetime, visit_type, created_at)
            VALUES (%s, CURRENT_TIMESTAMP, 'check_in', CURRENT_TIMESTAMP)
            RETURNING id;
        """, (user_id,))

        visit_id = cursor.fetchone()['id']
        conn.commit()

        return {
            "status": "success",
            "message": f"Пропуск {client_name} записан",
            "visit_id": visit_id
        }
    except Exception as e:
        conn.rollback()
        print(f"❌ Ошибка: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.get("/api/v1/cashier/today-passes")
def get_today_passes():
    """Получить все пропуски за сегодня"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT 
                v.id,
                u.name as client_name,
                v.visit_datetime,
                TO_CHAR(v.visit_datetime, 'HH24:MI') as visit_time_formatted
            FROM visits v
            JOIN users u ON v.user_id = u.id
            WHERE v.visit_datetime::date = CURRENT_DATE
            ORDER BY v.visit_datetime DESC
            LIMIT 20;
        """)
        return cursor.fetchall()
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
        return []
    finally:
        cursor.close()
        conn.close()

@app.get("/api/v1/cashier/stats")
def get_cashier_stats():
    """Получить статистику для кассира"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) as total FROM users;")
        total_users = cursor.fetchone()['total']

        cursor.execute("""
            SELECT COUNT(*) as active 
            FROM user_memberships 
            WHERE end_date >= CURRENT_DATE;
        """)
        active_memberships = cursor.fetchone()['active']

        cursor.execute("""
            SELECT COUNT(*) as today_passes 
            FROM visits 
            WHERE visit_datetime::date = CURRENT_DATE;
        """)
        today_passes = cursor.fetchone()['today_passes']

        return {
            "total_users": total_users,
            "active_memberships": active_memberships,
            "today_passes": today_passes
        }
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
        return {
            "total_users": 0,
            "active_memberships": 0,
            "today_passes": 0
        }
    finally:
        cursor.close()
        conn.close()

@app.post("/api/v1/cashier/assign-trainer")
def assign_trainer_to_client(data: dict):
    """Назначить тренера клиенту (с проверкой на 30 клиентов)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        client_id = data.get('client_id')
        coach_id = data.get('coach_id')

        if not client_id or not coach_id:
            raise HTTPException(status_code=400, detail="client_id и coach_id обязательны")

        cursor.execute("SELECT id, name FROM users WHERE id = %s;", (client_id,))
        client = cursor.fetchone()
        if not client:
            raise HTTPException(status_code=404, detail="Клиент не найден")

        cursor.execute("""
            SELECT c.id, u.name 
            FROM coaches c
            JOIN users u ON c.user_id = u.id
            WHERE c.id = %s;
        """, (coach_id,))
        coach = cursor.fetchone()
        if not coach:
            raise HTTPException(status_code=404, detail="Тренер не найден")
        
        # ===== ПРОВЕРКА НА 30 КЛИЕНТОВ =====
        cursor.execute("""
            SELECT COUNT(*) as count 
            FROM coach_clients 
            WHERE coach_id = %s AND is_active = true
        """, (coach_id,))
        result = cursor.fetchone()
        current_clients = result['count'] if result else 0
        
        if current_clients >= 30:
            raise HTTPException(
                status_code=400, 
                detail=f"У тренера {coach['name']} уже максимальное количество клиентов (30). Невозможно назначить нового клиента."
            )

        cursor.execute("""
            SELECT id, is_active FROM coach_clients 
            WHERE coach_id = %s AND client_id = %s
        """, (coach_id, client_id))

        existing = cursor.fetchone()

        if existing:
            if existing['is_active']:
                raise HTTPException(status_code=400, detail="Этот клиент уже назначен этому тренеру")
            else:
                cursor.execute("""
                    UPDATE coach_clients 
                    SET is_active = true, assigned_date = CURRENT_DATE
                    WHERE id = %s
                    RETURNING id;
                """, (existing['id'],))
                new_id = existing['id']
                print(f"✅ Реактивирована связь тренер {coach_id} - клиент {client_id}")
        else:
            cursor.execute("""
                INSERT INTO coach_clients (coach_id, client_id, assigned_date, is_active)
                VALUES (%s, %s, CURRENT_DATE, true)
                RETURNING id;
            """, (coach_id, client_id))
            new_id = cursor.fetchone()['id']
            print(f"✅ Создана новая связь тренер {coach_id} - клиент {client_id}")

        conn.commit()

        return {
            "status": "success",
            "message": f"Тренер {coach['name']} назначен клиенту {client['name']}. Всего клиентов у тренера: {current_clients + 1} из 30.",
            "coach_client_id": new_id,
            "total_clients": current_clients + 1
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        conn.rollback()
        print(f"❌ Ошибка: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.get("/api/v1/cashier/clients-without-trainer")
def get_clients_without_trainer():
    """Получить клиентов с активным абонементом, но без тренера"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT 
                u.id as user_id,
                u.name as client_name,
                u.email as client_email,
                m.name as membership_name,
                um.end_date,
                TO_CHAR(um.end_date, 'DD.MM.YYYY') as end_date_formatted
            FROM user_memberships um
            JOIN users u ON um.user_id = u.id
            JOIN memberships m ON um.membership_id = m.id
            WHERE um.end_date > CURRENT_DATE
              AND u.id NOT IN (
                  SELECT client_id 
                  FROM coach_clients 
                  WHERE is_active = true
              )
            ORDER BY u.name ASC;
        """)
        return cursor.fetchall()
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
        return []
    finally:
        cursor.close()
        conn.close()

# ==========================================
# ЗАЯВКИ НА АБОНЕМЕНТ
# ==========================================

class ApplicationCreate(BaseModel):
    identifier: str  # имя или email
    membership_name: str
    membership_price: float

@app.post("/api/v1/public/apply-membership")
def create_application(app: ApplicationCreate):
    """Создать заявку на абонемент (только для существующих клиентов)"""
    print("=" * 60)
    print("🔵 ПОЛУЧЕНА ЗАЯВКА НА АБОНЕМЕНТ")
    print(f"🔵 identifier: {app.identifier}")
    print(f"🔵 membership_name: {app.membership_name}")
    print(f"🔵 membership_price: {app.membership_price}")
    print("=" * 60)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Ищем пользователя по имени ИЛИ email
        cursor.execute("""
            SELECT id, name, email 
            FROM users 
            WHERE name ILIKE %s OR email ILIKE %s
            LIMIT 1;
        """, (f"%{app.identifier}%", f"%{app.identifier}%"))
        
        user = cursor.fetchone()
        print(f"🔍 Найден пользователь: {user}")
        
        if not user:
            print("❌ Пользователь не найден!")
            return {
                "status": "error",
                "message": "❌ Клиент не найден в системе. Пожалуйста, обратитесь в регистратуру для оформления абонемента."
            }
        
        # Проверяем, есть ли уже активный абонемент
        cursor.execute("""
            SELECT id FROM user_memberships 
            WHERE user_id = %s AND end_date >= CURRENT_DATE
        """, (user['id'],))
        
        active_membership = cursor.fetchone()
        print(f"🔍 Активный абонемент: {active_membership}")
        
        if active_membership:
            return {
                "status": "error",
                "message": f"⚠️ У {user['name']} уже есть активный абонемент! Обратитесь в регистратуру для продления."
            }
        
        # Проверяем, нет ли уже pending заявки от этого пользователя
        cursor.execute("""
            SELECT id FROM membership_applications 
            WHERE user_id = %s AND status = 'pending'
        """, (user['id'],))
        
        pending_app = cursor.fetchone()
        print(f"🔍 Pending заявка: {pending_app}")
        
        if pending_app:
            return {
                "status": "error",
                "message": "⏳ Ваша заявка уже отправлена и ожидает подтверждения кассира."
            }
        
        # Создаем заявку
        print("✅ Создание заявки...")
        cursor.execute("""
            INSERT INTO membership_applications 
            (user_id, membership_name, membership_price, status, created_at)
            VALUES (%s, %s, %s, 'pending', CURRENT_TIMESTAMP)
            RETURNING id;
        """, (user['id'], app.membership_name, app.membership_price))
        
        application_id = cursor.fetchone()['id']
        conn.commit()
        print(f"✅ Заявка создана! ID: {application_id}")
        
        return {
            "status": "success",
            "message": f"✅ Заявка отправлена! {user['name']}, ожидайте подтверждения от кассира.",
            "application_id": application_id,
            "user": {
                "id": user['id'],
                "name": user['name'],
                "email": user['email']
            }
        }
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Ошибка создания заявки: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": f"Ошибка: {str(e)}"}
    finally:
        cursor.close()
        conn.close()

@app.get("/api/v1/cashier/applications")
def get_membership_applications():
    """Получить все заявки на абонемент (для кассира)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT 
                ma.id,
                ma.user_id,
                u.name,
                u.email,
                ma.membership_name,
                ma.membership_price,
                ma.status,
                ma.created_at,
                ma.processed_at
            FROM membership_applications ma
            JOIN users u ON ma.user_id = u.id
            WHERE ma.status = 'pending'
            ORDER BY ma.created_at ASC;
        """)
        
        result = cursor.fetchall()
        return {"status": "success", "data": result}
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
        return {"status": "error", "message": str(e), "data": []}
    finally:
        cursor.close()
        conn.close()

@app.post("/api/v1/cashier/applications/{app_id}/approve")
def approve_application(app_id: int, data: dict):
    """Одобрить заявку и выдать абонемент"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Получаем заявку
        cursor.execute("""
            SELECT * FROM membership_applications 
            WHERE id = %s AND status = 'pending'
        """, (app_id,))
        
        application = cursor.fetchone()
        if not application:
            raise HTTPException(status_code=404, detail="Заявка не найдена или уже обработана")
        
        user_id = application['user_id']
        
        # Находим тариф по названию
        cursor.execute("""
            SELECT id, duration_days, price FROM memberships 
            WHERE name = %s
        """, (application['membership_name'],))
        
        membership = cursor.fetchone()
        if not membership:
            # Если тариф не найден, создаем временный
            cursor.execute("""
                INSERT INTO memberships (name, type, duration_days, price, description)
                VALUES (%s, 'Стандартный', 30, %s, 'Создан из заявки')
                RETURNING id;
            """, (application['membership_name'], application['membership_price']))
            membership_id = cursor.fetchone()['id']
            duration_days = 30
        else:
            membership_id = membership['id']
            duration_days = membership['duration_days']
        
        # Проверяем, есть ли уже активный абонемент
        cursor.execute("""
            SELECT id FROM user_memberships 
            WHERE user_id = %s AND end_date >= CURRENT_DATE
        """, (user_id,))
        
        existing_membership = cursor.fetchone()
        if existing_membership:
            # Деактивируем старый
            cursor.execute("""
                UPDATE user_memberships 
                SET end_date = CURRENT_DATE - INTERVAL '1 day' 
                WHERE id = %s;
            """, (existing_membership['id'],))
        
        # Создаем абонемент
        start_date = datetime.now().date()
        end_date = start_date + timedelta(days=duration_days)
        
        cursor.execute("""
            INSERT INTO user_memberships (user_id, membership_id, start_date, end_date, price_paid)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id;
        """, (user_id, membership_id, start_date, end_date, application['membership_price']))
        
        membership_id_new = cursor.fetchone()['id']
        
        # Обновляем статус заявки
        processed_by = data.get('processed_by')
        cursor.execute("""
            UPDATE membership_applications 
            SET status = 'approved', 
                processed_at = CURRENT_TIMESTAMP,
                processed_by = %s
            WHERE id = %s
            RETURNING id;
        """, (processed_by, app_id))
        
        conn.commit()
        
        # Получаем имя пользователя
        cursor.execute("SELECT name FROM users WHERE id = %s;", (user_id,))
        user = cursor.fetchone()
        
        return {
            "status": "success",
            "message": f"✅ Заявка одобрена! Абонемент выдан клиенту {user['name']}.",
            "user_id": user_id,
            "membership_id": membership_id_new
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        conn.rollback()
        print(f"❌ Ошибка: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.post("/api/v1/cashier/applications/{app_id}/reject")
def reject_application(app_id: int, data: dict):
    """Отклонить заявку"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE membership_applications 
            SET status = 'rejected', 
                processed_at = CURRENT_TIMESTAMP,
                processed_by = %s
            WHERE id = %s AND status = 'pending'
            RETURNING id;
        """, (data.get('processed_by'), app_id))
        
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Заявка не найдена или уже обработана")
        
        conn.commit()
        return {"status": "success", "message": "❌ Заявка отклонена"}
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Ошибка: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()
# ==========================================
# ГРУППЫ КЛИЕНТОВ
# ==========================================
# ВЫХОД ИЗ ГРУППЫ
@app.post("/api/v1/client/groups/{group_id}/leave")
def leave_group(group_id: int, data: dict):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        user_id = data.get('user_id')
        cursor.execute("""
            UPDATE group_members 
            SET is_active = false 
            WHERE group_id = %s AND user_id = %s
            RETURNING id;
        """, (group_id, user_id))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Вы не состоите в этой группе")
        conn.commit()
        return {"status": "success", "message": "Вы вышли из группы"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

# ВЫГНАТЬ УЧАСТНИКА (только для админа)
@app.post("/api/v1/client/groups/{group_id}/kick")
def kick_member(group_id: int, data: dict):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        user_id = data.get('user_id')
        admin_id = data.get('admin_id')
        
        # Проверяем, что админ является админом группы
        cursor.execute("""
            SELECT id FROM group_members 
            WHERE group_id = %s AND user_id = %s AND role = 'admin' AND is_active = true
        """, (group_id, admin_id))
        if not cursor.fetchone():
            raise HTTPException(status_code=403, detail="Только администратор может исключать участников")
        
        # Нельзя выгнать админа
        cursor.execute("""
            SELECT role FROM group_members 
            WHERE group_id = %s AND user_id = %s AND is_active = true
        """, (group_id, user_id))
        member = cursor.fetchone()
        if not member:
            raise HTTPException(status_code=404, detail="Участник не найден")
        if member['role'] == 'admin':
            raise HTTPException(status_code=403, detail="Нельзя исключить администратора")
        
        cursor.execute("""
            UPDATE group_members 
            SET is_active = false 
            WHERE group_id = %s AND user_id = %s
            RETURNING id;
        """, (group_id, user_id))
        conn.commit()
        return {"status": "success", "message": "Участник исключён из группы"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()
class GroupCreate(BaseModel):
    name: str
    goal: Optional[str] = None
    goal_exercise: Optional[str] = None
    goal_type: Optional[str] = "weight"
    goal_target: Optional[float] = None
    description: Optional[str] = None

class PersonalGoalCreate(BaseModel):
    goal: str
    exercise: str
    goal_type: str = "weight"
    target: float
    target_date: Optional[str] = None

class PersonalGoalProgress(BaseModel):
    value: float

class GroupInviteCreate(BaseModel):
    group_id: int
    invitee_id: int

# ==========================================
# ЛИЧНЫЕ ЦЕЛИ УЧАСТНИКОВ В ГРУППЕ
# ==========================================

class PersonalGoalCreate(BaseModel):
    goal: str
    exercise: str
    goal_type: str = "weight"
    target: float
    target_date: Optional[str] = None

class PersonalGoalProgress(BaseModel):
    value: float

@app.post("/api/v1/client/groups/{group_id}/personal-goal")
def set_personal_goal(group_id: int, client_id: int, goal: PersonalGoalCreate):
    """Установить личную цель участника в группе"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Проверяем, что участник состоит в группе
        cursor.execute("""
            SELECT id FROM group_members 
            WHERE group_id = %s AND user_id = %s AND is_active = true
        """, (group_id, client_id))
        
        if not cursor.fetchone():
            raise HTTPException(status_code=403, detail="Вы не являетесь участником группы")
        
        cursor.execute("""
            UPDATE group_members 
            SET personal_goal = %s,
                personal_goal_exercise = %s,
                personal_goal_type = %s,
                personal_goal_target = %s,
                personal_goal_current = 0,
                personal_goal_status = 'active',
                personal_goal_date = %s
            WHERE group_id = %s AND user_id = %s
            RETURNING id;
        """, (goal.goal, goal.exercise, goal.goal_type, goal.target, goal.target_date, group_id, client_id))
        
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Не удалось обновить цель")
        
        conn.commit()
        return {"status": "success", "message": "Личная цель установлена!"}
    except HTTPException as he:
        raise he
    except Exception as e:
        conn.rollback()
        print(f"❌ Ошибка: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.post("/api/v1/client/groups/{group_id}/personal-progress")
def update_personal_progress(group_id: int, data: dict):
    """Обновить прогресс по личной цели участника"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        user_id = data.get('user_id')
        value = data.get('value')
        
        if not user_id or value is None:
            raise HTTPException(status_code=400, detail="user_id и value обязательны")
        
        cursor.execute("""
            SELECT personal_goal_target, personal_goal_status FROM group_members 
            WHERE group_id = %s AND user_id = %s AND is_active = true
        """, (group_id, user_id))
        
        member = cursor.fetchone()
        if not member:
            raise HTTPException(status_code=403, detail="Участник не найден в группе")
        
        if member['personal_goal_status'] == 'achieved':
            raise HTTPException(status_code=400, detail="Цель уже достигнута!")
        
        target = member['personal_goal_target'] or 1
        new_status = 'achieved' if value >= target else 'active'
        
        cursor.execute("""
            UPDATE group_members 
            SET personal_goal_current = %s,
                personal_goal_status = %s
            WHERE group_id = %s AND user_id = %s
            RETURNING id;
        """, (value, new_status, group_id, user_id))
        
        conn.commit()
        return {"status": "success", "message": "Прогресс обновлен!"}
    except HTTPException as he:
        raise he
    except Exception as e:
        conn.rollback()
        print(f"❌ Ошибка: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.post("/api/v1/client/groups/{group_id}/common-progress")
def update_common_progress(group_id: int, data: dict):
    """Обновить прогресс по общей цели группы"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        user_id = data.get('user_id')
        value = data.get('value')
        
        if not user_id or value is None:
            raise HTTPException(status_code=400, detail="user_id и value обязательны")
        
        cursor.execute("""
            SELECT goal as common_goal_target FROM client_groups WHERE id = %s
        """, (group_id,))
        
        group = cursor.fetchone()
        if not group:
            raise HTTPException(status_code=404, detail="Группа не найдена")
        
        # Вместо числового target используем строку - просто отмечаем выполнение
        cursor.execute("""
            UPDATE group_members 
            SET common_progress = %s,
                common_completed = %s,
                common_completion_date = CASE WHEN %s THEN CURRENT_TIMESTAMP ELSE NULL END
            WHERE group_id = %s AND user_id = %s
            RETURNING id;
        """, (value, value == 100, value == 100, group_id, user_id))
        
        conn.commit()
        return {"status": "success", "message": "Прогресс обновлен!"}
    except HTTPException as he:
        raise he
    except Exception as e:
        conn.rollback()
        print(f"❌ Ошибка: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()
@app.post("/api/v1/client/{client_id}/groups")
def create_group(client_id: int, group: GroupCreate):
    """Создать новую группу (с общей целью или без)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM users WHERE id = %s", (client_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Клиент не найден")
        
        cursor.execute("""
            INSERT INTO client_groups (
                name, description, created_by,
                goal
            )
            VALUES (%s, %s, %s, %s)
            RETURNING id;
        """, (
            group.name, group.description, client_id,
            group.goal
        ))
        
        group_id = cursor.fetchone()['id']
        
        cursor.execute("""
            INSERT INTO group_members (group_id, user_id, role, is_active)
            VALUES (%s, %s, 'admin', true);
        """, (group_id, client_id))
        
        conn.commit()
        
        return {
            "status": "success",
            "message": "Группа успешно создана!",
            "group_id": group_id
        }
    except Exception as e:
        conn.rollback()
        print(f"❌ Ошибка: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.get("/api/v1/client/{client_id}/groups")
def get_client_groups(client_id: int):
    """Получить все группы клиента с деталями"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT 
                cg.id,
                cg.name,
                cg.description,
                cg.created_by,
                cg.created_at,
                cg.common_goal,
                cg.common_goal_exercise,
                cg.common_goal_type,
                cg.common_goal_target,
                u.name as created_by_name,
                COUNT(DISTINCT gm.user_id) as members_count,
                EXISTS (
                    SELECT 1 FROM group_members 
                    WHERE group_id = cg.id AND user_id = %s AND role = 'admin'
                ) as is_admin,
                (
                    SELECT common_progress FROM group_members 
                    WHERE group_id = cg.id AND user_id = %s
                ) as my_progress
            FROM client_groups cg
            JOIN group_members gm ON cg.id = gm.group_id
            LEFT JOIN users u ON cg.created_by = u.id
            WHERE gm.user_id = %s AND gm.is_active = true AND cg.is_active = true
            GROUP BY cg.id, cg.name, cg.description, cg.created_by, cg.created_at,
                     cg.common_goal, cg.common_goal_exercise, cg.common_goal_type,
                     cg.common_goal_target, u.name
            ORDER BY cg.created_at DESC;
        """, (client_id, client_id, client_id))
        
        result = cursor.fetchall()
        return {"status": "success", "data": result}
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
        return {"status": "error", "message": str(e), "data": []}
    finally:
        cursor.close()
        conn.close()

@app.get("/api/v1/client/{client_id}/group-invites")
def get_group_invites(client_id: int):
    """Получить все приглашения для клиента"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT 
                gi.id,
                gi.group_id,
                cg.name as group_name,
                gi.inviter_id,
                u.name as inviter_name,
                gi.status,
                gi.created_at
            FROM group_invites gi
            JOIN client_groups cg ON gi.group_id = cg.id
            JOIN users u ON gi.inviter_id = u.id
            WHERE gi.invitee_id = %s
            ORDER BY 
                CASE gi.status 
                    WHEN 'pending' THEN 1
                    WHEN 'accepted' THEN 2
                    WHEN 'rejected' THEN 3
                    ELSE 4
                END,
                gi.created_at DESC;
        """, (client_id,))
        
        result = cursor.fetchall()
        return {"status": "success", "data": result}
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
        return {"status": "error", "message": str(e), "data": []}
    finally:
        cursor.close()
        conn.close()

@app.post("/api/v1/client/{client_id}/invite")
def send_group_invite(client_id: int, invite: GroupInviteCreate):
    """Отправить приглашение в группу"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Проверяем, что отправитель является членом группы
        cursor.execute("""
            SELECT id FROM group_members 
            WHERE group_id = %s AND user_id = %s AND is_active = true
        """, (invite.group_id, client_id))
        
        if not cursor.fetchone():
            raise HTTPException(status_code=403, detail="Вы не являетесь участником этой группы")
        
        # Проверяем, что приглашаемый существует
        cursor.execute("SELECT id FROM users WHERE id = %s", (invite.invitee_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Пользователь не найден")
        
        # Проверяем, что пользователь уже не в группе
        cursor.execute("""
            SELECT id FROM group_members 
            WHERE group_id = %s AND user_id = %s AND is_active = true
        """, (invite.group_id, invite.invitee_id))
        
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Пользователь уже состоит в этой группе")
        
        # Проверяем, нет ли уже pending приглашения
        cursor.execute("""
            SELECT id FROM group_invites 
            WHERE group_id = %s AND invitee_id = %s AND status = 'pending'
        """, (invite.group_id, invite.invitee_id))
        
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Приглашение уже отправлено")
        
        # Создаем приглашение
        cursor.execute("""
            INSERT INTO group_invites (group_id, inviter_id, invitee_id, status)
            VALUES (%s, %s, %s, 'pending')
            RETURNING id;
        """, (invite.group_id, client_id, invite.invitee_id))
        
        invite_id = cursor.fetchone()['id']
        conn.commit()
        
        return {
            "status": "success",
            "message": "Приглашение отправлено!",
            "invite_id": invite_id
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        conn.rollback()
        print(f"❌ Ошибка: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.post("/api/v1/client/invites/{invite_id}/respond")
def respond_to_invite(invite_id: int, data: dict):
    """Ответить на приглашение (accept/reject)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        action = data.get('action')  # 'accept' или 'reject'
        client_id = data.get('client_id')
        
        if action not in ['accept', 'reject']:
            raise HTTPException(status_code=400, detail="Неверное действие")
        
        # Получаем приглашение
        cursor.execute("""
            SELECT * FROM group_invites 
            WHERE id = %s AND invitee_id = %s AND status = 'pending'
        """, (invite_id, client_id))
        
        invite = cursor.fetchone()
        if not invite:
            raise HTTPException(status_code=404, detail="Приглашение не найдено или уже обработано")
        
        if action == 'accept':
            # Добавляем пользователя в группу
            cursor.execute("""
                INSERT INTO group_members (group_id, user_id, role, is_active)
                VALUES (%s, %s, 'member', true)
                ON CONFLICT (group_id, user_id) DO UPDATE 
                SET is_active = true, joined_at = CURRENT_TIMESTAMP;
            """, (invite['group_id'], client_id))
            
            status = 'accepted'
            message = "Вы присоединились к группе!"
        else:
            status = 'rejected'
            message = "Приглашение отклонено"
        
        # Обновляем статус приглашения
        cursor.execute("""
            UPDATE group_invites 
            SET status = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING id;
        """, (status, invite_id))
        
        conn.commit()
        
        return {
            "status": "success",
            "message": message
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        conn.rollback()
        print(f"❌ Ошибка: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.delete("/api/v1/client/invites/{invite_id}")
def cancel_invite(invite_id: int, data: dict):
    """Отменить приглашение (только для отправителя)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        client_id = data.get('client_id')
        
        cursor.execute("""
            UPDATE group_invites 
            SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND inviter_id = %s AND status = 'pending'
            RETURNING id;
        """, (invite_id, client_id))
        
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Приглашение не найдено или не может быть отменено")
        
        conn.commit()
        return {"status": "success", "message": "Приглашение отменено"}
    except HTTPException as he:
        raise he
    except Exception as e:
        conn.rollback()
        print(f"❌ Ошибка: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.get("/api/v1/client/{client_id}/group-competitions")
def get_group_competitions(client_id: int):
    """Получить соревнования в группах клиента"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT 
                cg.id as group_id,
                cg.name as group_name,
                gc.id as competition_id,
                gc.user_id,
                u.name as user_name,
                gc.goal_id,
                g.exercise_id,
                e.name as exercise_name,
                g.target_value,
                g.current_value,
                g.goal_type,
                gc.progress_value,
                gc.completion_date,
                gc.is_winner,
                (g.current_value / NULLIF(g.target_value, 0) * 100) as progress_percent,
                CASE 
                    WHEN g.current_value >= g.target_value AND g.status = 'achieved' THEN 'completed'
                    WHEN g.current_value >= g.target_value THEN 'completed'
                    ELSE 'in_progress'
                END as goal_status
            FROM group_competitions gc
            JOIN client_groups cg ON gc.group_id = cg.id
            JOIN users u ON gc.user_id = u.id
            JOIN client_goals g ON gc.goal_id = g.id
            LEFT JOIN exercises e ON g.exercise_id = e.id
            WHERE cg.id IN (
                SELECT group_id FROM group_members 
                WHERE user_id = %s AND is_active = true
            )
            AND gc.is_winner = false
            ORDER BY 
                cg.name,
                gc.progress_value DESC,
                g.target_value ASC;
        """, (client_id,))
        
        result = cursor.fetchall()
        return {"status": "success", "data": result}
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
        return {"status": "error", "message": str(e), "data": []}
    finally:
        cursor.close()
        conn.close()

@app.post("/api/v1/client/competitions/{competition_id}/complete")
def complete_competition(competition_id: int, data: dict):
    """Отметить цель как выполненную в соревновании"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        client_id = data.get('client_id')
        
        # Проверяем, что пользователь участвует в этом соревновании
        cursor.execute("""
            SELECT id, user_id FROM group_competitions 
            WHERE id = %s AND user_id = %s
        """, (competition_id, client_id))
        
        comp = cursor.fetchone()
        if not comp:
            raise HTTPException(status_code=404, detail="Соревнование не найдено")
        
        # Отмечаем как выполненное
        cursor.execute("""
            UPDATE group_competitions 
            SET completion_date = CURRENT_TIMESTAMP, 
                is_winner = true,
                progress_value = (
                    SELECT current_value FROM client_goals 
                    WHERE id = (SELECT goal_id FROM group_competitions WHERE id = %s)
                )
            WHERE id = %s
            RETURNING id;
        """, (competition_id, competition_id))
        
        conn.commit()
        return {"status": "success", "message": "Цель выполнена! 🎉"}
    except HTTPException as he:
        raise he
    except Exception as e:
        conn.rollback()
        print(f"❌ Ошибка: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()
# ==========================================
# ЦЕЛИ ДЛЯ ТРЕНЕРА
# ==========================================

@app.get("/api/v1/coach/{coach_id}/goals")
def get_coach_goals(coach_id: int):
    """Получить все цели тренера"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Получаем user_id тренера
        cursor.execute("SELECT user_id FROM coaches WHERE id = %s;", (coach_id,))
        coach = cursor.fetchone()
        if not coach:
            return {"status": "error", "message": "Тренер не найден", "data": []}
        
        user_id = coach['user_id']
        
        cursor.execute("""
            SELECT 
                g.id,
                g.user_id,
                g.exercise_id,
                e.name as exercise_name,
                g.goal_type,
                g.target_value,
                g.current_value,
                g.start_date,
                g.target_date,
                g.status,
                g.description,
                g.created_at,
                (SELECT value FROM goal_progress 
                 WHERE goal_id = g.id 
                 ORDER BY progress_date DESC 
                 LIMIT 1) as last_progress_value,
                (SELECT progress_date FROM goal_progress 
                 WHERE goal_id = g.id 
                 ORDER BY progress_date DESC 
                 LIMIT 1) as last_progress_date,
                CASE 
                    WHEN g.status = 'achieved' THEN 'Достигнута ✅'
                    WHEN g.status = 'active' AND g.current_value >= g.target_value THEN 'Достигнута ✅'
                    WHEN g.status = 'active' THEN 'В процессе 🏃'
                    WHEN g.status = 'failed' THEN 'Не выполнена ❌'
                    WHEN g.status = 'cancelled' THEN 'Отменена ⛔'
                    ELSE g.status
                END as status_display
            FROM client_goals g
            LEFT JOIN exercises e ON g.exercise_id = e.id
            WHERE g.user_id = %s
            ORDER BY 
                CASE g.status 
                    WHEN 'active' THEN 1
                    WHEN 'achieved' THEN 2
                    ELSE 3
                END,
                g.created_at DESC;
        """, (user_id,))

        result = cursor.fetchall()
        return {"status": "success", "data": result}

    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
        return {"status": "error", "message": str(e), "data": []}
    finally:
        cursor.close()
        conn.close()

@app.post("/api/v1/coach/{coach_id}/goals")
def create_coach_goal(coach_id: int, goal: GoalCreate):
    """Создать цель для тренера"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Получаем user_id тренера
        cursor.execute("SELECT user_id FROM coaches WHERE id = %s;", (coach_id,))
        coach = cursor.fetchone()
        if not coach:
            raise HTTPException(status_code=404, detail="Тренер не найден")
        
        user_id = coach['user_id']

        exercise_id = goal.exercise_id
        if not exercise_id and goal.exercise_name:
            cursor.execute(
                "SELECT id FROM exercises WHERE name ILIKE %s LIMIT 1;",
                (f"%{goal.exercise_name}%",)
            )
            exercise = cursor.fetchone()
            if exercise:
                exercise_id = exercise['id']
            else:
                cursor.execute(
                    "INSERT INTO exercises (name) VALUES (%s) RETURNING id;",
                    (goal.exercise_name,)
                )
                exercise_id = cursor.fetchone()['id']

        cursor.execute("""
            INSERT INTO client_goals (
                user_id, exercise_id, goal_type, target_value, 
                target_date, description, status
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'active')
            RETURNING id;
        """, (
            user_id,
            exercise_id,
            goal.goal_type,
            goal.target_value,
            goal.target_date,
            goal.description
        ))

        goal_id = cursor.fetchone()['id']
        conn.commit()

        return {
            "status": "success",
            "message": "Цель успешно создана!",
            "goal_id": goal_id
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        conn.rollback()
        print(f"❌ Ошибка: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.post("/api/v1/coach/goals/{goal_id}/progress")
def add_coach_goal_progress(goal_id: int, progress: GoalProgressAdd):
    """Добавить прогресс к цели тренера"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id, user_id, target_value, current_value 
            FROM client_goals 
            WHERE id = %s AND status = 'active';
        """, (goal_id,))

        goal = cursor.fetchone()
        if not goal:
            raise HTTPException(status_code=404, detail="Цель не найдена или неактивна")

        progress_date = progress.progress_date or datetime.now().date().isoformat()

        cursor.execute("""
            INSERT INTO goal_progress (goal_id, value, progress_date, note)
            VALUES (%s, %s, %s, %s)
            RETURNING id;
        """, (goal_id, progress.value, progress_date, progress.note))

        progress_id = cursor.fetchone()['id']

        new_current = max(goal['current_value'] or 0, progress.value)
        cursor.execute("""
            UPDATE client_goals 
            SET current_value = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s;
        """, (new_current, goal_id))

        if new_current >= goal['target_value']:
            cursor.execute("""
                UPDATE client_goals 
                SET status = 'achieved', updated_at = CURRENT_TIMESTAMP
                WHERE id = %s;
            """, (goal_id,))

        conn.commit()

        return {
            "status": "success",
            "message": "Прогресс добавлен!",
            "progress_id": progress_id,
            "current_value": new_current,
            "target_value": goal['target_value'],
            "is_achieved": new_current >= goal['target_value']
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        conn.rollback()
        print(f"❌ Ошибка: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.delete("/api/v1/coach/goals/{goal_id}")
def delete_coach_goal(goal_id: int):
    """Удалить цель тренера"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM goal_progress WHERE goal_id = %s;", (goal_id,))
        cursor.execute("DELETE FROM client_goals WHERE id = %s RETURNING id;", (goal_id,))

        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Цель не найдена")

        conn.commit()
        return {"status": "success", "message": "Цель удалена"}

    except HTTPException as he:
        raise he
    except Exception as e:
        conn.rollback()
        print(f"❌ Ошибка: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

# ==========================================
# ОТЗЫВЫ ТРЕНЕРА НА СВОИ ТРЕНИРОВКИ
# ==========================================

@app.get("/api/v1/coach/{coach_id}/sessions")
def get_coach_sessions(coach_id: int):
    """Получить все тренировки тренера (где он был клиентом)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT 
                s.id AS session_id,
                s.session_datetime,
                s.session_type,
                s.duration_minutes,
                u.name AS coach_name,
                s.is_coached,
                s.client_feedback,
                s.wellbeing_score
            FROM sessions s
            LEFT JOIN coaches c ON s.coach_id = c.id
            LEFT JOIN users u ON c.user_id = u.id
            WHERE s.user_id = (SELECT user_id FROM coaches WHERE id = %s)
            ORDER BY s.session_datetime DESC;
        """, (coach_id,))
        
        result = cursor.fetchall()
        return {"status": "success", "data": result}
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
        return {"status": "error", "message": str(e), "data": []}
    finally:
        cursor.close()
        conn.close()

@app.patch("/api/v1/coach/sessions/{session_id}/feedback")
def leave_coach_feedback(session_id: int, feedback: FeedbackCreate):
    """Тренер оставляет отзыв на свою тренировку"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, user_id FROM sessions WHERE id = %s;", (session_id,))
        session = cursor.fetchone()
        if not session:
            raise HTTPException(status_code=404, detail="Тренировка не найдена")

        cursor.execute("""
            UPDATE sessions
            SET client_feedback = %s, wellbeing_score = %s
            WHERE id = %s
            RETURNING id;
        """, (feedback.feedback_text, feedback.wellbeing_score, session_id))

        conn.commit()
        return {
            "status": "success",
            "message": "Спасибо за отзыв!",
            "session_id": session_id
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        conn.rollback()
        print(f"❌ Ошибка: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()
        # ==========================================
# ВСЕ ОТЗЫВЫ ТРЕНЕРА (свои + клиентов)
# ==========================================

@app.get("/api/v1/coach/{coach_id}/all-feedback")
def get_all_coach_feedback(coach_id: int):
    """Получить все отзывы тренера (свои + от клиентов)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Получаем список клиентов тренера
        cursor.execute("""
            SELECT client_id FROM coach_clients 
            WHERE coach_id = %s AND is_active = true
        """, (coach_id,))
        clients = cursor.fetchall()
        client_ids = [str(c['client_id']) for c in clients] if clients else []
        
        # Добавляем самого тренера (чтобы видеть свои отзывы)
        cursor.execute("SELECT user_id FROM coaches WHERE id = %s", (coach_id,))
        coach = cursor.fetchone()
        if coach:
            client_ids.append(str(coach['user_id']))
        
        # Если нет никого - возвращаем пустой результат
        if not client_ids:
            return {"status": "success", "data": []}
        
        ids_str = ','.join(client_ids)
        
        # Получаем все тренировки с отзывами для этих пользователей
        cursor.execute(f"""
            SELECT 
                s.id as session_id,
                s.user_id,
                u.name as client_name,
                s.session_datetime,
                s.session_type,
                s.client_feedback,
                s.wellbeing_score,
                s.duration_minutes,
                CASE 
                    WHEN s.user_id = (SELECT user_id FROM coaches WHERE id = %s) THEN 'my'
                    ELSE 'client'
                END as feedback_source
            FROM sessions s
            JOIN users u ON s.user_id = u.id
            WHERE s.user_id IN ({ids_str})
              AND s.client_feedback IS NOT NULL 
              AND s.client_feedback != ''
            ORDER BY s.session_datetime DESC
            LIMIT 50;
        """, (coach_id,))
        
        result = cursor.fetchall()
        return {"status": "success", "data": result}
        
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e), "data": []}
    finally:
        cursor.close()
        conn.close()
# ==========================================
# ПРОВЕРКА КОЛИЧЕСТВА КЛИЕНТОВ У ТРЕНЕРА
# ==========================================

@app.get("/api/v1/coach/{coach_id}/clients-count")
def get_coach_clients_count(coach_id: int):
    """Получить количество активных клиентов у тренера"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT COUNT(*) as count 
            FROM coach_clients 
            WHERE coach_id = %s AND is_active = true
        """, (coach_id,))
        result = cursor.fetchone()
        return {"count": result['count'] if result else 0}
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
        return {"count": 0}
    finally:
        cursor.close()
        conn.close()

# ==========================================
# ОБНОВЛЕННЫЙ СПИСОК КЛИЕНТОВ ТРЕНЕРА (с статусом абонемента)
# ==========================================

@app.get("/api/v1/coach/{coach_id}/clients-with-status")
def get_coach_clients_with_status(coach_id: int):
    """Получить список клиентов тренера с статусом абонемента"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT 
                u.id as client_id,
                u.name as client_name,
                u.email as client_email,
                cc.assigned_date,
                (
                    SELECT COUNT(*) 
                    FROM sessions s 
                    WHERE s.user_id = u.id
                ) as total_sessions,
                (
                    SELECT m.name 
                    FROM user_memberships um
                    JOIN memberships m ON um.membership_id = m.id
                    WHERE um.user_id = u.id AND um.end_date >= CURRENT_DATE
                    LIMIT 1
                ) as membership_name,
                (
                    SELECT um.end_date
                    FROM user_memberships um
                    WHERE um.user_id = u.id AND um.end_date >= CURRENT_DATE
                    LIMIT 1
                ) as membership_end_date,
                CASE 
                    WHEN um.id IS NOT NULL AND um.end_date >= CURRENT_DATE THEN 'active'
                    WHEN um.id IS NOT NULL AND um.end_date < CURRENT_DATE THEN 'expired'
                    ELSE 'no_membership'
                END as membership_status
            FROM coach_clients cc
            JOIN users u ON cc.client_id = u.id
            LEFT JOIN user_memberships um ON u.id = um.user_id AND um.end_date >= CURRENT_DATE
            WHERE cc.coach_id = %s AND cc.is_active = true
            ORDER BY 
                CASE 
                    WHEN um.id IS NOT NULL AND um.end_date >= CURRENT_DATE THEN 1
                    WHEN um.id IS NOT NULL AND um.end_date < CURRENT_DATE THEN 2
                    ELSE 3
                END,
                u.name ASC;
        """, (coach_id,))

        result = cursor.fetchall()
        print(f"✅ Найдено клиентов для тренера {coach_id}: {len(result)}")
        return {"status": "success", "data": result}
    except Exception as e:
        print(f"❌ Ошибка получения клиентов: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()



# ==========================================
# ГРУППЫ - РАСШИРЕННЫЕ ЭНДПОИНТЫ (НОВЫЕ)
# ==========================================

@app.get("/api/v1/client/groups/{group_id}/detail")
def get_group_detail(group_id: int):
    """Получить детальную информацию о группе с участниками и их целями"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Получаем информацию о группе
        cursor.execute("""
            SELECT 
                cg.id, cg.name, cg.description, 
                cg.goal as common_goal,
                cg.created_by, cg.created_at,
                u.name as creator_name
            FROM client_groups cg
            LEFT JOIN users u ON cg.created_by = u.id
            WHERE cg.id = %s AND cg.is_active = true
        """, (group_id,))
        
        group = cursor.fetchone()
        if not group:
            raise HTTPException(status_code=404, detail="Группа не найдена")
        
        # Получаем участников с их целями
        cursor.execute("""
            SELECT 
                gm.user_id,
                u.name,
                u.email,
                gm.role,
                gm.joined_at,
                gm.personal_goal,
                gm.personal_goal_exercise,
                gm.personal_goal_type,
                gm.personal_goal_target,
                gm.personal_goal_current,
                gm.personal_goal_status,
                gm.personal_goal_date,
                gm.common_progress,
                gm.common_completed,
                gm.common_completion_date
            FROM group_members gm
            JOIN users u ON gm.user_id = u.id
            WHERE gm.group_id = %s AND gm.is_active = true
            ORDER BY gm.role DESC, gm.common_progress DESC, u.name ASC
        """, (group_id,))
        
        members = cursor.fetchall()
        
        # Формируем результат
        result = dict(group)
        result['members'] = [dict(m) for m in members]
        
        return {"status": "success", "data": result}
        
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.post("/api/v1/client/groups/{group_id}/personal-goal")
def set_personal_goal(group_id: int, client_id: int, goal: PersonalGoalCreate):
    """Установить личную цель участника в группе"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Проверяем, что участник состоит в группе
        cursor.execute("""
            SELECT id FROM group_members 
            WHERE group_id = %s AND user_id = %s AND is_active = true
        """, (group_id, client_id))
        
        if not cursor.fetchone():
            raise HTTPException(status_code=403, detail="Вы не являетесь участником группы")
        
        cursor.execute("""
            UPDATE group_members 
            SET personal_goal = %s,
                personal_goal_exercise = %s,
                personal_goal_type = %s,
                personal_goal_target = %s,
                personal_goal_current = 0,
                personal_goal_status = 'active',
                personal_goal_date = %s
            WHERE group_id = %s AND user_id = %s
            RETURNING id;
        """, (goal.goal, goal.exercise, goal.goal_type, goal.target, goal.target_date, group_id, client_id))
        
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Не удалось обновить цель")
        
        conn.commit()
        return {"status": "success", "message": "Личная цель установлена!"}
    except HTTPException as he:
        raise he
    except Exception as e:
        conn.rollback()
        print(f"❌ Ошибка: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.post("/api/v1/client/groups/{group_id}/personal-progress")
def update_personal_progress(group_id: int, data: dict):
    """Обновить прогресс по личной цели участника"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        user_id = data.get('user_id')
        value = data.get('value')
        
        if not user_id or value is None:
            raise HTTPException(status_code=400, detail="user_id и value обязательны")
        
        cursor.execute("""
            SELECT personal_goal_target, personal_goal_status FROM group_members 
            WHERE group_id = %s AND user_id = %s AND is_active = true
        """, (group_id, user_id))
        
        member = cursor.fetchone()
        if not member:
            raise HTTPException(status_code=403, detail="Участник не найден в группе")
        
        if member['personal_goal_status'] == 'achieved':
            raise HTTPException(status_code=400, detail="Цель уже достигнута!")
        
        target = member['personal_goal_target'] or 1
        new_status = 'achieved' if value >= target else 'active'
        
        cursor.execute("""
            UPDATE group_members 
            SET personal_goal_current = %s,
                personal_goal_status = %s
            WHERE group_id = %s AND user_id = %s
            RETURNING id;
        """, (value, new_status, group_id, user_id))
        
        conn.commit()
        return {"status": "success", "message": "Прогресс обновлен!"}
    except HTTPException as he:
        raise he
    except Exception as e:
        conn.rollback()
        print(f"❌ Ошибка: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.post("/api/v1/client/groups/{group_id}/common-progress")
def update_common_progress(group_id: int, data: dict):
    """Обновить прогресс по общей цели группы"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        user_id = data.get('user_id')
        value = data.get('value')
        
        if not user_id or value is None:
            raise HTTPException(status_code=400, detail="user_id и value обязательны")
        
        cursor.execute("""
            SELECT common_goal_target FROM client_groups WHERE id = %s
        """, (group_id,))
        
        group = cursor.fetchone()
        if not group:
            raise HTTPException(status_code=404, detail="Группа не найдена")
        
        if not group['common_goal_target']:
            raise HTTPException(status_code=400, detail="У группы нет общей цели")
        
        target = group['common_goal_target']
        is_completed = value >= target
        
        cursor.execute("""
            UPDATE group_members 
            SET common_progress = %s,
                common_completed = %s,
                common_completion_date = CASE WHEN %s THEN CURRENT_TIMESTAMP ELSE NULL END
            WHERE group_id = %s AND user_id = %s
            RETURNING id;
        """, (value, is_completed, is_completed, group_id, user_id))
        
        conn.commit()
        return {"status": "success", "message": "Прогресс обновлен!"}
    except HTTPException as he:
        raise he
    except Exception as e:
        conn.rollback()
        print(f"❌ Ошибка: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()
@app.get("/api/v1/client/groups/{group_id}/messages")
def get_group_messages(group_id: int, limit: int = 50):
    """Получить сообщения чата группы"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT 
                gm.id,
                gm.group_id,
                gm.user_id,
                u.name as user_name,
                gm.message,
                gm.created_at
            FROM group_messages gm
            JOIN users u ON gm.user_id = u.id
            WHERE gm.group_id = %s
            ORDER BY gm.created_at ASC
            LIMIT %s
        """, (group_id, limit))
        
        result = cursor.fetchall()
        return {"status": "success", "data": result}
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
        return {"status": "error", "message": str(e), "data": []}
    finally:
        cursor.close()
        conn.close()


@app.post("/api/v1/client/groups/{group_id}/messages")
def send_group_message(group_id: int, data: dict):
    """Отправить сообщение в чат группы"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        user_id = data.get('user_id')
        message = data.get('message', '').strip()
        
        if not user_id or not message:
            raise HTTPException(status_code=400, detail="user_id и message обязательны")
        
        cursor.execute("""
            SELECT id FROM group_members 
            WHERE group_id = %s AND user_id = %s AND is_active = true
        """, (group_id, user_id))
        
        if not cursor.fetchone():
            raise HTTPException(status_code=403, detail="Вы не являетесь участником группы")
        
        cursor.execute("""
            INSERT INTO group_messages (group_id, user_id, message)
            VALUES (%s, %s, %s)
            RETURNING id
        """, (group_id, user_id, message))
        
        msg_id = cursor.fetchone()['id']
        conn.commit()
        
        return {"status": "success", "message": "Сообщение отправлено", "message_id": msg_id}
    except HTTPException as he:
        raise he
    except Exception as e:
        conn.rollback()
        print(f"❌ Ошибка: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()


@app.get("/api/v1/client/search-users")
def search_users(q: str):
    """Поиск пользователей по имени или email (все пользователи)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id, name, email
            FROM users
            WHERE (name ILIKE %s OR email ILIKE %s)
            ORDER BY name ASC
            LIMIT 10
        """, (f"%{q}%", f"%{q}%"))
        
        result = cursor.fetchall()
        return {"status": "success", "data": result}
    except Exception as e:
        print(f"❌ Ошибка поиска: {str(e)}")
        return {"status": "error", "message": str(e), "data": []}
    finally:
        cursor.close()
        conn.close()



# ==========================================
# СТАТИЧЕСКИЕ ФАЙЛЫ (ВСЕГДА В КОНЦЕ!)
# ==========================================

@app.get("/")
async def read_root():
    """Главная страница - index.html"""
    file_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(file_path):
        return FileResponse(file_path)
    return HTMLResponse(f"""
    <h1>Файл index.html не найден</h1>
    <p>Ищем по пути: {file_path}</p>
    <p>Файлы в папке frontend: {os.listdir(FRONTEND_DIR) if os.path.exists(FRONTEND_DIR) else 'Папка не найдена'}</p>
    """)

@app.get("/{file_path:path}")
async def serve_file(file_path: str):
    """Раздача всех статических файлов"""
    # Защита от directory traversal
    if '..' in file_path:
        raise HTTPException(status_code=403, detail="Forbidden")

    # Разрешенные расширения
    allowed_extensions = ('.html', '.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.webp')

    # Если файл имеет разрешенное расширение
    if any(file_path.endswith(ext) for ext in allowed_extensions):
        full_path = os.path.join(FRONTEND_DIR, file_path)
        if os.path.exists(full_path) and os.path.isfile(full_path):
            return FileResponse(full_path)

    # Если файл не найден
    raise HTTPException(status_code=404, detail=f"File not found: {file_path}")


# ==========================================
# ЗАПУСК
# ==========================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=True)