from flask import Flask, jsonify, request, render_template, session, redirect, url_for
from urllib.parse import urlparse, urljoin
from functools import wraps
from werkzeug.utils import secure_filename
import json
import os
import urllib.request
import math
import uuid
from datetime import datetime, timedelta, timezone

# app.py はプロジェクト直下に置く。
# 実体（templates / static / data）は bousai_app/ 配下にあるので、そこを参照する。
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.join(BASE_DIR, 'bousai_app')

app = Flask(
    __name__,
    template_folder=os.path.join(APP_DIR, 'templates'),
    static_folder=os.path.join(APP_DIR, 'static'),
)
app.secret_key = 'your-secret-key-here'

# 管理者認証情報
ADMIN_CREDENTIALS = {
    'admin': '123'
}

# ────────────────────────────────
# 気象警報・注意報設定
PREFECTURE_CODE = "020000"  # 青森県
AREA_NAME = "青森市"

# JMA の新形式警報・注意報JSONでは、青森市は 0220100（県内市区町村コード）で表現される。
# 旧形式の 1420500 では一致しないため、正しいコードへ修正する。
AREA_CODE = "0220100"

WARNING_URL = (
    f"https://www.jma.go.jp/bosai/warning/data/r8/{PREFECTURE_CODE}.json"
)

JST = timezone(timedelta(hours=9))
DEFAULT_LOCATION = (35.3390, 139.4903)

# 警報・注意報のコード一覧
WARNING_CODES = {
    "00": "解除",
    "02": "暴風雪警報",
    "03": "レベル3大雨警報",
    "04": "洪水警報",
    "05": "暴風警報",
    "06": "大雪警報",
    "07": "波浪警報",
    "08": "レベル3高潮警報",
    "09": "レベル3土砂災害警報",
    "10": "レベル2大雨注意報",
    "12": "大雪注意報",
    "13": "風雪注意報",
    "14": "雷注意報",
    "15": "強風注意報",
    "16": "波浪注意報",
    "17": "融雪注意報",
    "18": "洪水注意報",
    "19": "レベル2高潮注意報",
    "20": "濃霧注意報",
    "21": "乾燥注意報",
    "22": "なだれ注意報",
    "23": "低温注意報",
    "24": "霜注意報",
    "25": "着氷注意報",
    "26": "着雪注意報",
    "27": "その他の注意報",
    "29": "レベル2土砂災害注意報",
    "32": "暴風雪特別警報",
    "33": "レベル5大雨特別警報",
    "35": "暴風特別警報",
    "36": "大雪特別警報",
    "37": "波浪特別警報",
    "38": "レベル5高潮特別警報",
    "39": "レベル5土砂災害特別警報",
    "43": "レベル4大雨危険警報",
    "48": "レベル4高潮危険警報",
    "49": "レベル4土砂災害危険警報"
}

# ────────────────────────────────
# サンプルデータの読み込み
DATA_FILE = os.path.join(APP_DIR, 'data', 'shelters.json')
INSTRUCTIONS_FILE = os.path.join(APP_DIR, 'data', 'instructions.json')
UPLOAD_FOLDER = os.path.join(APP_DIR, 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def load_json(path, default):
    """JSONファイルを読み込む（存在しない・壊れている場合は default を返す）"""
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default

shelters = load_json(DATA_FILE, [])
instructions = load_json(INSTRUCTIONS_FILE, [])

def save_instructions():
    """指示ボードのデータをファイルに保存する"""
    try:
        with open(INSTRUCTIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(instructions, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def save_uploaded_image(file_storage):
    """アップロードされた画像を static/uploads に保存し、URLを返す"""
    if not file_storage or not file_storage.filename:
        return ''

    allowed_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
    ext = os.path.splitext(file_storage.filename)[1].lower()
    if ext not in allowed_extensions:
        return ''

    filename = secure_filename(file_storage.filename)
    timestamp = datetime.now(JST).strftime('%Y%m%d%H%M%S')
    unique_name = f"{timestamp}_{filename}"
    save_path = os.path.join(UPLOAD_FOLDER, unique_name)
    file_storage.save(save_path)
    return url_for('static', filename=f'uploads/{unique_name}')


def save_shelter_image(file_storage):
    """登録画面用に画像形式を検証し、一意なファイル名で保存する"""
    if not file_storage or not file_storage.filename:
        return '', None

    allowed_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
    extension = os.path.splitext(file_storage.filename)[1].lower()
    content_type = (file_storage.content_type or '').lower()
    if extension not in allowed_extensions or not content_type.startswith('image/'):
        return None, '画像ファイル（PNG、JPG、GIF、WEBP）のみ登録できます。'

    if not secure_filename(file_storage.filename):
        return None, '画像ファイル名を処理できませんでした。'
    unique_name = f"shelter_{uuid.uuid4().hex}{extension}"
    save_path = os.path.join(UPLOAD_FOLDER, unique_name)
    try:
        file_storage.save(save_path)
    except Exception:
        return None, '画像の保存に失敗しました。登録内容は保存されていません。'
    return url_for('static', filename=f'uploads/{unique_name}'), save_path


def shelter_form_values():
    """登録フォームの再表示用にPOST値を取得する"""
    return {
        'name': request.form.get('name', ''),
        'address': request.form.get('address', ''),
        'facilities': request.form.getlist('facilities'),
        'damages': request.form.getlist('damages'),
        'congestion': request.form.get('congestion', ''),
    }
# ────────────────────────────────

# ────────────────────────────────
# 認証関連の設定とヘルパー関数
def is_safe_url(target):
    """リダイレクト先URLが安全かどうかチェック"""
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc

def login_required(f):
    """認証が必要なページに付けるデコレータ"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            # 現在のURLをnextパラメータとしてログイン画面にリダイレクト
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def get_japan_time():
    """日本時間（JST）の現在時刻を取得する"""
    return datetime.now(JST).strftime("%Y年%m月%d日 %H:%M")


def format_report_time(iso_str):
    """気象庁の発表時刻（ISO形式）をJSTの表示用文字列に変換する"""
    if not iso_str:
        return "不明"
    try:
        parsed = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        if parsed.tzinfo:
            parsed = parsed.astimezone(JST)
        return parsed.strftime("%Y年%m月%d日 %H:%M")
    except ValueError:
        return iso_str


FACILITY_LABELS = {
    'pet_allowed': 'ペット可',
    'barrier_free': 'バリアフリー',
    'climate_control': '冷暖房機器',
    'infection_control': '感染症対策設備',
    'english_support': '英語対応可',
}

def _clean_query_values(values):
    """GETパラメータの空白を除去し、空値を除外する"""
    return [value.strip() for value in values if isinstance(value, str) and value.strip()]


def _has_available_space(shelter):
    """定員情報が正しい数値で、空きがある場合だけTrueを返す"""
    facilities = shelter.get('facilities')
    if not isinstance(facilities, dict):
        facilities = {}

    capacity = facilities.get('capacity')
    occupancy = facilities.get('current_occupancy')
    valid_number = lambda value: isinstance(value, (int, float)) and not isinstance(value, bool)
    return (
        valid_number(capacity)
        and valid_number(occupancy)
        and capacity > 0
        and occupancy < capacity
    )


def _shelter_status(shelter):
    """明示された状態、または定員から表示用の満空状態を求める"""
    if shelter.get('status') in ('available', 'full'):
        return shelter['status']
    facilities = shelter.get('facilities')
    if isinstance(facilities, dict):
        capacity = facilities.get('capacity')
        occupancy = facilities.get('current_occupancy')
        if (isinstance(capacity, (int, float)) and not isinstance(capacity, bool)
                and isinstance(occupancy, (int, float)) and not isinstance(occupancy, bool)
                and capacity > 0 and occupancy >= capacity):
            return 'full'
    return 'available'


def _valid_coordinate(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _distance_km(origin, destination):
    """2点間の直線距離をkmで計算する"""
    latitude1, longitude1 = map(math.radians, origin)
    latitude2, longitude2 = map(math.radians, destination)
    delta_latitude = latitude2 - latitude1
    delta_longitude = longitude2 - longitude1
    haversine = (math.sin(delta_latitude / 2) ** 2
                 + math.cos(latitude1) * math.cos(latitude2)
                 * math.sin(delta_longitude / 2) ** 2)
    return 6371 * 2 * math.asin(math.sqrt(haversine))


def prepare_shelter_results(results):
    """検索結果に座標・状態・距離を補完し、近い順に返す"""
    prepared = []
    for index, shelter in enumerate(results):
        item = dict(shelter)
        latitude = shelter.get('latitude')
        longitude = shelter.get('longitude')
        if not (_valid_coordinate(latitude) and _valid_coordinate(longitude)):
            offset = (index + 1) * 0.004
            latitude = DEFAULT_LOCATION[0] + offset
            longitude = DEFAULT_LOCATION[1] + offset * 0.7
        item['latitude'] = latitude
        item['longitude'] = longitude
        item['status'] = _shelter_status(shelter)
        item['distance_km'] = round(_distance_km(DEFAULT_LOCATION, (latitude, longitude)), 1)
        prepared.append(item)
    return sorted(prepared, key=lambda shelter: shelter['distance_km'])


def filter_shelters(district=None, name=None, areas=None, facilities=None):
    """複数の検索条件を、カテゴリ間AND・カテゴリ内仕様で適用する"""
    name = (name or '').strip().casefold()
    district = (district or '').strip().casefold()
    areas = set(_clean_query_values(areas or []))
    facilities = set(_clean_query_values(facilities or []))
    filtered = []
    for shelter in shelters:
        shelter_name = str(shelter.get('name', '')).casefold()
        shelter_district = str(shelter.get('district', '')).casefold()
        if name and name not in shelter_name:
            continue
        if district and district not in shelter_district:
            continue
        if areas and not any(area.casefold() in shelter_district for area in areas):
            continue

        shelter_facilities = shelter.get('facilities')
        if not isinstance(shelter_facilities, dict):
            shelter_facilities = {}
        if not all(
            _has_available_space(shelter)
            if facility == 'available_only'
            else shelter_facilities.get(facility) is True
            for facility in facilities
        ):
            continue
        filtered.append(shelter)
    return filtered


def parse_area_warnings(warning_data):
    """気象庁の新形式JSONから対象市区町村の発表・継続中の情報を抽出する"""
    if not isinstance(warning_data, list):
        raise ValueError("気象庁の警報・注意報データが新形式の配列ではありません")

    warnings = []
    seen_codes = set()
    report_datetimes = []

    for report in warning_data:
        if not isinstance(report, dict):
            continue

        report_datetime = report.get("reportDatetime")
        if isinstance(report_datetime, str) and report_datetime:
            report_datetimes.append(report_datetime)

        warning = report.get("warning")
        if not isinstance(warning, dict):
            continue

        class20_items = warning.get("class20Items", [])
        if not isinstance(class20_items, list):
            continue

        area = next(
            (
                item for item in class20_items
                if isinstance(item, dict)
                and item.get("areaCode") == AREA_CODE
            ),
            None
        )
        if not area:
            continue

        kinds = area.get("kinds", [])
        if not isinstance(kinds, list):
            continue

        for kind in kinds:
            if not isinstance(kind, dict):
                continue

            status = kind.get("status", "")
            code = kind.get("code", "")
            if status not in ("発表", "継続") or not code or code in seen_codes:
                continue

            warnings.append({
                "name": WARNING_CODES.get(
                    code,
                    f"不明な警報・注意報 (コード: {code})"
                ),
                "code": code,
                "status": status
            })
            seen_codes.add(code)

    latest_report_datetime = max(report_datetimes, default="")
    return warnings, latest_report_datetime


def get_weather_warnings():
    """対象市区町村の警報・注意報を取得する"""
    try:
        # 青森県の新形式（令和8年～）警報・注意報データを取得
        with urllib.request.urlopen(url=WARNING_URL, timeout=10) as res:
            warning_data = json.loads(res.read())

        warnings, report_datetime = parse_area_warnings(warning_data)

        return {
            "area_name": AREA_NAME,
            "warnings": warnings,
            "report_time": format_report_time(report_datetime),
            "last_fetch_time": get_japan_time()
        }

    except Exception:
        return {
            "area_name": AREA_NAME,
            "warnings": [],
            "report_time": "取得失敗",
            "last_fetch_time": get_japan_time(),
            "error": True
        }


# トップページ：templates/index.html を返す（住民向け指示も表示する）
@app.route('/')
def index():
    resident_notices = [
        i for i in instructions
        if i.get('target') in ('住民', '全住民')
    ]
    return render_template('index.html', resident_notices=resident_notices)

# ログインページ
@app.route('/login', methods=['GET', 'POST'])
def login():
    # リダイレクト先を取得（指定がなければホーム）
    next_url = request.args.get('next') or request.form.get('next')

    # 安全でないURLの場合はデフォルトページにリダイレクト
    if not next_url or not is_safe_url(next_url):
        next_url = url_for('index')

    if request.method == 'POST':
        password = request.form.get('password', '').strip()

        # 認証チェック
        username = next(
            (name for name, registered_password in ADMIN_CREDENTIALS.items()
             if registered_password == password),
            None
        )
        if username:
            session['logged_in'] = True
            session['username'] = username
            # ログイン成功後は指定されたページにリダイレクト
            return redirect(next_url)
        return render_template('login.html', error=True, message="パスワードが正しくありません。", next=next_url)

    # ログイン済みの場合は指定されたページにリダイレクト
    if session.get('logged_in'):
        return redirect(next_url)

    return render_template('login.html', next=next_url)

# ログアウト
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# 避難所登録ページ
@app.route('/shelter_register', methods=['GET', 'POST'])
@login_required
def shelter_register():
    form_values = {
        'name': '',
        'address': '',
        'facilities': [],
        'damages': [],
        'congestion': '',
    }
    errors = []
    registered = request.args.get('registered') == '1'

    if request.method == 'POST':
        form_values = shelter_form_values()
        form_values['name'] = form_values['name'].strip()
        form_values['address'] = form_values['address'].strip()

        if not form_values['name']:
            errors.append('避難所名を入力してください。')
        if not form_values['address']:
            errors.append('避難所住所を入力してください。')
        if form_values['congestion'] not in ('空いている', '通常', '混雑', '満員'):
            errors.append('混雑状況を選択してください。')

        image_url, image_path = save_shelter_image(request.files.get('image'))
        if image_url is None:
            errors.append(image_path)

        if errors:
            return render_template(
                'shelter_register.html',
                message='入力内容を確認してください。',
                success=False,
                error=True,
                errors=errors,
                form_values=form_values,
            )

        new_id = max((int(s.get('id', 0)) for s in shelters), default=0) + 1
        now = datetime.now(JST).strftime('%Y-%m-%dT%H:%M:%S%z')
        new_shelter = {
            'id': new_id,
            'name': form_values['name'],
            'address': form_values['address'],
            'facilities': form_values['facilities'],
            'damages': form_values['damages'],
            'congestion': form_values['congestion'],
            'status': 'full' if form_values['congestion'] == '満員' else 'available',
            'image': image_url or '',
            'created_at': now,
            'updated_at': now,
        }
        shelters.append(new_shelter)

        try:
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(shelters, f, ensure_ascii=False, indent=2)
        except Exception:
            shelters.pop()
            if image_path:
                try:
                    os.remove(image_path)
                except OSError:
                    pass
            return render_template(
                'shelter_register.html',
                message='避難所情報の保存に失敗しました。登録内容は保存されていません。',
                success=False,
                error=True,
                errors=['データ保存に失敗しました。時間をおいて再試行してください。'],
                form_values=form_values,
            ), 500

        return redirect(url_for('shelter_register', registered='1'))

    return render_template(
        'shelter_register.html',
        message='避難所を登録しました。' if registered else '登録済みの避難所情報を確認・追加できます。',
        success=registered,
        error=False,
        errors=errors,
        form_values=form_values,
    )

# 避難所検索ページ
@app.route('/shelter_search')
def shelter_search():
    return render_template(
        'shelter_search.html',
        selected_areas=_clean_query_values(request.args.getlist('areas')),
        selected_facilities=_clean_query_values(request.args.getlist('facilities')),
    )

# 全施設一覧ページ
@app.route('/all_shelters')
def all_shelters():
    return render_search_results(shelters, '')


# 指示ボード：住民向けの指示を一覧で確認する
@app.route('/board', methods=['GET', 'POST'])
@login_required
def board():
    success_message = None

    if request.method == 'POST':
        targets = request.form.getlist('targets') or [request.form.get('targets', '全住民')]
        channels = request.form.getlist('channels') or [request.form.get('channels', 'アプリ')]
        urgency = request.form.get('urgency', 'お知らせ')
        message = (request.form.get('message', '') or '').strip()
        uploaded_image = request.files.get('image')
        image_url = save_uploaded_image(uploaded_image)

        if message:
            target_map = {
                '全住民': '全住民',
                '北部のみ': '北部',
                '南部のみ': '南側',
                '庁内・消防団': '庁内'
            }
            target_value = next(
                (target_map.get(target, target) for target in targets if target in target_map),
                '全住民'
            )
            urgency_map = {
                '即時避難': '🔴即時避難',
                '警戒・準備': '🟡警戒・準備',
                'お知らせ': '🔵お知らせ'
            }
            new_id = max((int(i.get('id', 0)) for i in instructions), default=0) + 1
            now = datetime.now(JST).strftime('%Y/%m/%d %H:%M')
            instructions.insert(0, {
                'id': new_id,
                'target': target_value,
                'content': message,
                'shelter': '',
                'status': urgency_map.get(urgency, urgency),
                'created_at': now,
                'updated_at': now,
                'channels': channels,
                'urgency': urgency,
                'image_url': image_url,
            })
            save_instructions()
            success_message = '発信が登録されました。'

    default_history = [
        {
            'created_at': '2026/09/02 10:15',
            'status': '【🔴即時避難】',
            'content': '南側地区における土砂災害警戒について',
            'target': '南側',
            'image_url': 'https://images.unsplash.com/photo-1500375592092-40eb2168fd21?auto=format&fit=crop&w=900&q=80'
        },
        {
            'created_at': '2026/09/01 18:00',
            'status': '【🔵お知らせ】',
            'content': '明日の大雨に備えた確認のお願い',
            'target': '全住民',
            'image_url': ''
        },
        {
            'created_at': '2026/08/30 09:00',
            'status': '【🟡警戒・準備】',
            'content': '第1避難所の定員到達に関するお知らせ',
            'target': '全住民',
            'image_url': 'https://images.unsplash.com/photo-1489515217757-5fd1be406fef?auto=format&fit=crop&w=900&q=80'
        }
    ]

    history_entries = list(instructions) or list(default_history)
    items_per_page = 3
    total_history = len(history_entries)
    total_pages = max(1, (total_history + items_per_page - 1) // items_per_page)
    try:
        current_page = int(request.args.get('page', 1))
    except (TypeError, ValueError):
        current_page = 1
    current_page = min(max(current_page, 1), total_pages)
    start_index = (current_page - 1) * items_per_page
    page_entries = history_entries[start_index:start_index + items_per_page]

    return render_template(
        'board.html',
        instructions=page_entries,
        message=success_message,
        current_page=current_page,
        total_pages=total_pages,
        total_history=total_history,
        all_history=history_entries,
        has_previous=current_page > 1,
        has_next=current_page < total_pages,
    )

# 検索結果ページ：templates/search_results.html を返す
@app.route('/search_results')
def search_results():
    results = filter_shelters(
        name=request.args.get('name'),
        district=request.args.get('district'),
        areas=request.args.getlist('areas'),
        facilities=request.args.getlist('facilities'),
    )
    return render_search_results(results, request.query_string.decode('utf-8'))


def render_search_results(results, search_query):
    prepared_results = prepare_shelter_results(results)
    return render_template(
        'search_results.html',
        results=prepared_results,
        search_query=search_query,
        map_data=prepared_results,
        current_location={'latitude': DEFAULT_LOCATION[0], 'longitude': DEFAULT_LOCATION[1]},
    )

# JSON API：/shelters?district=地区名
@app.route('/shelters', methods=['GET'])
def get_shelters():
    results = filter_shelters(district=request.args.get('district'))

    if not results:
        # 見つからなければエラー JSON を返す
        return jsonify({'error': 'No shelters found'}), 404

    # 見つかったらリストを JSON で返す
    return jsonify(results)

# 気象警報・注意報API
@app.route('/api/weather_warnings')
def api_weather_warnings():
    """気象警報・注意報をJSON形式で返すAPI"""
    return jsonify(get_weather_warnings())

if __name__ == '__main__':
    app.run(debug=True, port=5000)
