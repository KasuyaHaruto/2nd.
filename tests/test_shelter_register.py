import unittest

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

    def test_post_registers_shelter_and_shows_success_message(self):
        response = self.client.post('/shelter_register', data={'name': 'テスト避難所'})
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('避難所を登録しました。', html)

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
        self.assertIn('2026/09/02 10:15', html)

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

    def test_board_page_has_upload_and_filter_controls(self):
        response = self.client.get('/board')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('type="file"', html)
        self.assertIn('data-history-item', html)
        self.assertIn('history-search', html)
        self.assertIn('historyPreview', html)
        self.assertIn('data-image-url', html)

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
