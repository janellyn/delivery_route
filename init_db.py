from app import create_app
from extensions import db
from models import User, RecentLocation, RouteHistory

app = create_app()
with app.app_context():
    db.create_all()
    print("База даних та таблиці успішно створені!")
