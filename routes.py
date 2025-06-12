from flask import redirect, url_for, Blueprint, render_template, request
from flask_login import current_user, login_required
from datetime import datetime
import flexpolyline as fp
import requests

from models import RouteHistory, RecentLocation, db

routes_bp = Blueprint('routes', __name__)

HERE_API_KEY = 'kH-Fy4yVm0G72HaOsR4iI6_p4cK0jV9UCsX4TyJ8-BU'
WEATHER_API_KEY = '5c6f39e6773cffb20551bd6362273d40'



def geocode_address(address):
    url = 'https://geocode.search.hereapi.com/v1/geocode'
    params = {
        'q': address,
        'apiKey': HERE_API_KEY,
        'limit': 1
    }
    response = requests.get(url, params=params)
    if response.ok and response.json().get('items'):
        pos = response.json()['items'][0]['position']
        return [pos['lng'], pos['lat']]
    return None

def get_weather(lat, lon):
    url = "http://api.openweathermap.org/data/2.5/weather"
    params = {
        'lat': lat,
        'lon': lon,
        'appid': WEATHER_API_KEY,
        'units': 'metric',
        'lang': 'ua'
    }
    response = requests.get(url, params=params)
    if response.ok:
        data = response.json()
        return f"{data['weather'][0]['description'].capitalize()}, {data['main']['temp']}°C"
    return "Погода недоступна"


def decode_here_polyline(polyline_str):
    decoded = fp.decode(polyline_str)
    return [[lat, lon] for lat, lon in decoded]


def get_route_data(coords_list, route_type):
    base_url = "https://router.hereapi.com/v8/routes"
    origin = f"{coords_list[0][1]},{coords_list[0][0]}"
    destination = f"{coords_list[-1][1]},{coords_list[-1][0]}"
    routing_mode = "car" if route_type == "road" else "pedestrian"

    via_params = ''
    if len(coords_list) > 2:
        via = coords_list[1:-1]
        via_params = '&' + '&'.join([f'via={coords[1]},{coords[0]}' for coords in via])

    url = (
        f"{base_url}?transportMode={routing_mode}"
        f"&origin={origin}"
        f"{via_params}"
        f"&destination={destination}"
        f"&return=summary,polyline"
        f"&routingMode=fast"
        f"&alternatives=3"
        f"&apiKey={HERE_API_KEY}"
        f"&traffic=true"
    )

    response = requests.get(url)
    if not response.ok:
        print(f"Помилка HERE API: {response.status_code} {response.text}")
        return None, None, None, None, None

    data = response.json()
    routes = []

    for route in data['routes']:
        sections = route['sections']
        distance_m = sum(section['summary']['length'] for section in sections)
        
        if routing_mode == "car":
            duration_sec = distance_m / 4000 * 3600
        else:
            duration_sec = sum(section['summary']['duration'] for section in sections)

        duration_no_traffic = duration_sec * 0.7
        delay_factor = duration_sec / duration_no_traffic

        traffic_status = (
            'critical' if delay_factor > 2.5 else
            'warning' if delay_factor > 1.5 else
            'ok'
        )

        all_coords = []
        for section in sections:
            encoded_polyline = section['polyline']
            coords = decode_here_polyline(encoded_polyline)
            all_coords.extend(coords)

        routes.append({
            'duration': round(duration_sec / 60, 2),
            'distance': round(distance_m / 1000, 2),
            'geometry': all_coords,
            'traffic_status': traffic_status
        })

    return routes


@routes_bp.route('/route', methods=['GET', 'POST'])
@login_required
def calculate_route():
    if request.method == 'POST':
        origin = request.form.get('origin')
        destination = request.form.get('destination')
        waypoints_raw = request.form.getlist('waypoints')
        route_type = request.form.get("route_type")

        origin_coords = geocode_address(origin)
        destination_coords = geocode_address(destination)
        waypoint_coords = [geocode_address(wp) for wp in waypoints_raw if wp.strip()]

        if not (origin_coords and destination_coords and all(waypoint_coords)):
            return render_template('route_result.html', error="Не вдалося геокодувати адреси.")

        coords = [origin_coords] + waypoint_coords + [destination_coords]
        points = [origin] + [wp for wp in waypoints_raw if wp.strip()] + [destination]

        routes = get_route_data(coords, route_type)
        if not routes:
            return render_template('route_result.html', error="Не вдалося отримати маршрут.")

        weather = get_weather(origin_coords[1], origin_coords[0])
        best_route = routes[0]

        db.session.add(RouteHistory(
            user_id=current_user.id,
            origin=origin,
            destination=destination,
            distance=best_route['distance'],
            duration=best_route['duration'],
            timestamp=datetime.utcnow()
        ))
        db.session.add(RecentLocation(
            user_id=current_user.id,
            origin=origin,
            destination=destination
        ))
        db.session.commit()

        return render_template('route_result.html',
                origin=origin,
                destination=destination,
                points=points,
                coords=coords,
                weather=weather,
                stops=len(coords),
                routes=routes,
                duration=best_route['duration'],
                distance=best_route['distance'],
                traffic_status=best_route['traffic_status'],
                route_type=route_type)

    recent_locations = RecentLocation.query.filter_by(user_id=current_user.id).order_by(RecentLocation.created_at.desc()).limit(5).all()
    return render_template('route_form.html', recent_locations=recent_locations)


@routes_bp.route('/history')
@login_required
def history():
    routes = RouteHistory.query.filter_by(user_id=current_user.id).order_by(RouteHistory.timestamp).all()
    return render_template('history.html',
                           history=routes,
                           labels=[r.timestamp.strftime('%d.%m') for r in routes],
                           distances=[r.distance for r in routes],
                           durations=[r.duration for r in routes])


@routes_bp.route('/delete/<int:route_id>', methods=['POST'])
@login_required
def delete_route(route_id):
    route = RouteHistory.query.filter_by(id=route_id, user_id=current_user.id).first()
    if route:
        db.session.delete(route)
        db.session.commit()
        return '', 204 
    return '', 404


@routes_bp.route('/')
def dashboard():
    return render_template('index.html')
