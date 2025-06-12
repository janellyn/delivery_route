from flask import Flask
from extensions import db, login_manager

def create_app():
    app = Flask(__name__)

    app.config['SECRET_KEY'] = 'your-secret-key'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///routes.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login' 

    from auth import auth_bp
    from routes import routes_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(routes_bp)

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
