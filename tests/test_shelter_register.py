import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch

import app as app_module
from app import app


class ShelterRegisterPageTest(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess['logged_in'] = True
            sess['username'] = 'admin'

    def test_get_page_shows_registration_prompt(self):
        response = self.client.get('/shelter_register')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('新しい避難所情報を登録します。避難所名を入力してください。', html)
        self.assertIn('避難所名（必須）', html)

    def test_safety_confirmation_is_saved_and_counted_for_admin(self):
        with tempfile.TemporaryDirectory() as directory:
            data_file = os.path.join(directory, 'safety_confirmations.json')
            confirmations = []
            with patch.object(app_module, 'safety_confirmations', confirmations), \
                    patch.object(app_module, 'SAFETY_CONFIRMATIONS_FILE', data_file):
                response = self.client.post('/api/safety_confirmations')
                self.assertEqual(response.status_code, 201)
                self.assertEqual(response.json['message'], '安否確認を登録しました。')
                with open(data_file, encoding='utf-8') as file:
                    self.assertEqual(len(json.load(file)), 1)
                home = self.client.get('/')
                self.assertIn('ワンタッチ安否確認：<strong>1</strong> 件', home.get_data(as_text=True))

    def test_safety_count_is_not_shown_to_public_users(self):
        with patch.object(app_module, 'safety_confirmations', [{'created_at': 'now'}]):
            html = self.client.get('/logout', follow_redirects=True).get_data(as_text=True)
            self.assertNotIn('管理者ステータス', html)

    def test_safety_confirmation_toggles_without_duplicate_count(self):
        with tempfile.TemporaryDirectory() as directory:
            data_file = os.path.join(directory, 'safety_confirmations.json')
            confirmations = []
            with patch.object(app_module, 'safety_confirmations', confirmations), \
                    patch.object(app_module, 'SAFETY_CONFIRMATIONS_FILE', data_file):
                payload = {'client_id': 'browser-1', 'status': 'on'}
                self.assertEqual(self.client.post('/api/safety_confirmations', json=payload).json['count'], 1)
                self.assertEqual(self.client.post('/api/safety_confirmations', json=payload).json['count'], 1)
                off = self.client.post('/api/safety_confirmations', json={**payload, 'status': 'off'})
                self.assertEqual(off.json['status'], 'off')
                self.assertEqual(off.json['count'], 0)
                self.assertEqual(confirmations[0]['status'], 'off')

    def test_post_registers_shelter_and_shows_success_message(self):
        response = self.client.post('/shelter_register', data={
            'name': 'テスト避難所',
            'address': '藤沢市朝日町1-1',
            'congestion': '通常',
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('避難所を登録しました。', html)

    def test_registration_requires_address_and_congestion(self):
        response = self.client.post('/shelter_register', data={'name': '入力不足'})
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('避難所住所を入力してください。', html)
        self.assertIn('混雑状況を選択してください。', html)

    def test_registration_rejects_non_image_upload(self):
        response = self.client.post('/shelter_register', data={
            'name': 'ファイル検証施設',
            'address': '藤沢市中央2-2',
            'congestion': '通常',
            'image': (io.BytesIO(b'not-an-image'), 'notes.txt'),
        }, content_type='multipart/form-data')
        self.assertEqual(response.status_code, 200)
        self.assertIn('画像ファイル（PNG、JPG、GIF、WEBP）のみ登録できます。', response.get_data(as_text=True))

    def test_registration_persists_all_values_and_image(self):
        with tempfile.TemporaryDirectory() as directory:
            data_file = os.path.join(directory, 'shelters.json')
            upload_folder = os.path.join(directory, 'uploads')
            os.makedirs(upload_folder)
            shelters = []
            with patch.object(app_module, 'shelters', shelters), \
                    patch.object(app_module, 'DATA_FILE', data_file), \
                    patch.object(app_module, 'UPLOAD_FOLDER', upload_folder):
                response = self.client.post('/shelter_register', data={
                    'name': '  新しい避難所  ',
                    'address': '  藤沢市中央1-1  ',
                    'facilities': ['pet_allowed', 'locker'],
                    'damages': ['electricity', 'food'],
                    'congestion': '空いている',
                    'image': (io.BytesIO(b'fake-png'), 'shelter.png'),
                }, content_type='multipart/form-data', follow_redirects=True)
                self.assertEqual(response.status_code, 200)
                self.assertIn('避難所を登録しました。', response.get_data(as_text=True))
                with open(data_file, encoding='utf-8') as file:
                    saved = json.load(file)
                self.assertEqual(saved[0]['name'], '新しい避難所')
                self.assertEqual(saved[0]['address'], '藤沢市中央1-1')
                self.assertEqual(saved[0]['facilities'], ['pet_allowed', 'locker'])
                self.assertEqual(saved[0]['damages'], ['electricity', 'food'])
                self.assertTrue(saved[0]['image'].startswith('/static/uploads/'))
                self.assertEqual(len(os.listdir(upload_folder)), 1)

    def test_registration_persists_geocoded_coordinates(self):
        with tempfile.TemporaryDirectory() as directory:
            data_file = os.path.join(directory, 'shelters.json')
            with patch.object(app_module, 'shelters', []), \
                    patch.object(app_module, 'DATA_FILE', data_file), \
                    patch.object(app_module, 'geocode_address', return_value=(35.3381, 139.4892)):
                response = self.client.post('/shelter_register', data={
                    'name': '番地テスト避難所',
                    'address': '藤沢市朝日町1-1',
                    'congestion': '通常',
                })

                self.assertEqual(response.status_code, 302)
                with open(data_file, encoding='utf-8') as file:
                    saved = json.load(file)
                self.assertEqual(saved[0]['latitude'], 35.3381)
                self.assertEqual(saved[0]['longitude'], 139.4892)

    def test_edit_updates_shelter_values_and_regeocodes_changed_address(self):
        with tempfile.TemporaryDirectory() as directory:
            data_file = os.path.join(directory, 'shelters.json')
            shelters = [{
                'id': 4, 'name': '旧施設', 'address': '藤沢市中央1-1',
                'facilities': ['locker'], 'damages': ['food'],
                'congestion': '通常', 'status': 'available', 'image': '',
                'latitude': 35.3, 'longitude': 139.4,
            }]
            with patch.object(app_module, 'shelters', shelters), \
                    patch.object(app_module, 'DATA_FILE', data_file), \
                    patch.object(app_module, 'geocode_address', return_value=(35.4, 139.5)):
                response = self.client.post('/shelter/4/edit', data={
                    'name': '更新施設', 'address': '藤沢市朝日町1-1',
                    'facilities': 'pet_allowed', 'damages': 'electricity',
                    'congestion': '混雑',
                })
                self.assertEqual(response.status_code, 302)
                with open(data_file, encoding='utf-8') as file:
                    saved = json.load(file)
                self.assertEqual(saved[0]['name'], '更新施設')
                self.assertEqual(saved[0]['facilities'], ['pet_allowed'])
                self.assertEqual(saved[0]['latitude'], 35.4)
                self.assertEqual(saved[0]['longitude'], 139.5)

    def test_delete_removes_shelter_and_managed_image(self):
        with tempfile.TemporaryDirectory() as directory:
            data_file = os.path.join(directory, 'shelters.json')
            upload_folder = os.path.join(directory, 'uploads')
            os.makedirs(upload_folder)
            image_path = os.path.join(upload_folder, 'shelter_old.png')
            with open(image_path, 'wb') as file:
                file.write(b'image')
            shelters = [{'id': 5, 'name': '削除施設', 'image': '/static/uploads/shelter_old.png'}]
            with patch.object(app_module, 'shelters', shelters), \
                    patch.object(app_module, 'DATA_FILE', data_file), \
                    patch.object(app_module, 'UPLOAD_FOLDER', upload_folder):
                response = self.client.post('/shelter/5/delete')
                self.assertEqual(response.status_code, 302)
                self.assertEqual(shelters, [])
                self.assertFalse(os.path.exists(image_path))
                with open(data_file, encoding='utf-8') as file:
                    self.assertEqual(json.load(file), [])

    def test_registration_requires_login(self):
        client = app.test_client()
        response = client.get('/shelter_register')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login?next=', response.headers['Location'])

    def test_board_page_displays_instruction_board_controls(self):
        response = self.client.get('/board')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('📢新規発信', html)
        self.assertIn('[送信先]', html)
        self.assertIn('[発信手段]', html)
        self.assertIn('即時避難', html)
        self.assertIn('プレビュー確認する', html)
        self.assertIn('キーワードで過去の指示を検索', html)
        self.assertRegex(html, r'\d+ / \d+ ページ（全\d+件）')

    def test_board_history_pagination_uses_requested_page(self):
        first_page = self.client.get('/board?page=1')
        second_page = self.client.get('/board?page=2')

        self.assertEqual(first_page.status_code, 200)
        self.assertEqual(second_page.status_code, 200)
        self.assertIn('1 / ', first_page.get_data(as_text=True))
        self.assertIn('2 / ', second_page.get_data(as_text=True))
        self.assertIn('次の3件 ▶', first_page.get_data(as_text=True))
        self.assertIn('◀ 前の3件', second_page.get_data(as_text=True))

    def test_board_post_saves_message_to_history(self):
        response = self.client.post('/board', data={
            'targets': '南部のみ',
            'channels': 'アプリ',
            'urgency': '即時避難',
            'message': '南側地区における土砂災害警戒について'
        })
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('南側地区における土砂災害警戒について', html)
        self.assertIn('発信が登録されました', html)

    def test_board_history_can_be_edited(self):
        with tempfile.TemporaryDirectory() as directory:
            data_file = os.path.join(directory, 'instructions.json')
            history = [{
                'id': 8, 'target': '南側', 'content': '変更前',
                'status': '🔵お知らせ', 'created_at': '2026/09/03 10:00',
                'updated_at': '2026/09/03 10:00', 'channels': ['アプリ'],
                'urgency': 'お知らせ', 'image_url': '',
            }]
            with patch.object(app_module, 'instructions', history), \
                    patch.object(app_module, 'INSTRUCTIONS_FILE', data_file):
                response = self.client.post('/board', data={
                    'edit_id': '8', 'targets': '北部のみ', 'channels': 'SNS',
                    'urgency': '即時避難', 'message': '変更後の発信',
                })
                self.assertEqual(response.status_code, 200)
                self.assertIn('発信履歴を更新しました。', response.get_data(as_text=True))
                with open(data_file, encoding='utf-8') as file:
                    saved = json.load(file)
                self.assertEqual(saved[0]['content'], '変更後の発信')
                self.assertEqual(saved[0]['target'], '北部')
                self.assertEqual(saved[0]['urgency'], '即時避難')

    def test_board_history_can_be_deleted(self):
        with tempfile.TemporaryDirectory() as directory:
            data_file = os.path.join(directory, 'instructions.json')
            history = [{'id': 9, 'content': '削除対象', 'image_url': ''}]
            with patch.object(app_module, 'instructions', history), \
                    patch.object(app_module, 'INSTRUCTIONS_FILE', data_file):
                response = self.client.post('/board/9/delete', follow_redirects=True)
                self.assertEqual(response.status_code, 200)
                self.assertIn('発信履歴を削除しました。', response.get_data(as_text=True))
                self.assertEqual(history, [])

    def test_board_history_shows_edit_and_delete_controls(self):
        original_instructions = app_module.instructions
        try:
            app_module.instructions = [{'id': 10, 'content': '操作対象', 'target': '全住民', 'status': '🔵お知らせ', 'created_at': 'now'}]
            html = self.client.get('/board').get_data(as_text=True)
            self.assertIn('data-edit-instruction="10"', html)
            self.assertIn('/board/10/delete', html)
        finally:
            app_module.instructions = original_instructions

    def test_board_page_has_upload_and_filter_controls(self):
        response = self.client.get('/board')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('type="file"', html)
        self.assertIn('data-history-item', html)
        self.assertIn('history-search', html)
        self.assertIn('historyPreview', html)
        self.assertIn('data-image-url', html)
        self.assertIn('imageLightbox', html)
        self.assertIn('添付画像の全画面表示', html)
        self.assertIn('messagePreviewModal', html)
        self.assertIn('messagePreviewTargets', html)
        self.assertIn('messagePreviewChannels', html)
        self.assertIn('messagePreviewUrgency', html)
        self.assertIn('messagePreviewContent', html)
        self.assertIn('messagePreviewImage', html)

    def test_board_post_saves_uploaded_image_and_shows_preview_url(self):
        response = self.client.post(
            '/board',
            data={
                'targets': '全住民',
                'channels': 'アプリ',
                'urgency': 'お知らせ',
                'message': '画像付きの発信テスト',
                'image': (io.BytesIO(b'fake-image-data'), 'sample.png')
            },
            content_type='multipart/form-data'
        )
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('画像付きの発信テスト', html)
        self.assertIn('/static/uploads/', html)

    def test_parse_area_warnings_uses_aomori_city_code(self):
        from app import parse_area_warnings

        warning_data = [{
            'reportDatetime': '2026-09-02T11:17:00+09:00',
            'warning': {
                'class20Items': [{
                    'areaCode': '0220100',
                    'kinds': [{'code': '10', 'status': '継続'}]
                }]
            }
        }]

        warnings, report_datetime = parse_area_warnings(warning_data)

        self.assertEqual(report_datetime, '2026-09-02T11:17:00+09:00')
        self.assertEqual(warnings[0]['name'], 'レベル2大雨注意報')
        self.assertEqual(warnings[0]['status'], '継続')


if __name__ == '__main__':
    unittest.main()
