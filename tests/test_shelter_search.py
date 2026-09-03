import unittest

import app as app_module


class ShelterSearchTest(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()
        self.original_shelters = app_module.shelters
        app_module.shelters = [
            {
                'id': 1,
                'name': '中央体育館',
                'district': '北部中央',
                'address': '中央1-1-1',
                'facilities': {
                    'pet_allowed': True,
                    'barrier_free': True,
                    'capacity': 100,
                    'current_occupancy': 20,
                },
            },
            {
                'id': 2,
                'name': '東部学校',
                'district': '東部',
                'facilities': {
                    'pet_allowed': True,
                    'capacity': 100,
                    'current_occupancy': 100,
                },
            },
            {'id': 3, 'name': '設備なし施設', 'district': '西部'},
            {
                'id': 4,
                'name': '定員不正施設',
                'district': '南部',
                'facilities': {'capacity': '不明', 'current_occupancy': 0},
            },
        ]

    def tearDown(self):
        app_module.shelters = self.original_shelters

    def test_search_uses_area_or_and_facility_and(self):
        results = app_module.filter_shelters(
            areas=['北部', '東部'],
            facilities=['pet_allowed', 'available_only'],
        )
        self.assertEqual([shelter['id'] for shelter in results], [1])

    def test_search_handles_missing_and_invalid_capacity(self):
        self.assertEqual(
            app_module.filter_shelters(facilities=['available_only']),
            [app_module.shelters[0]],
        )

    def test_search_page_restores_get_values_and_result_escapes_html(self):
        response = self.client.get('/shelter_search?areas=北部&facilities=pet_allowed')
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn('name="areas" value="北部" checked', html)
        self.assertIn('name="facilities" value="pet_allowed" checked', html)

        app_module.shelters[0]['name'] = '<中央体育館>'
        response = self.client.get('/search_results?name=%E4%B8%AD%E5%A4%AE')
        html = response.get_data(as_text=True)
        self.assertIn('&lt;中央体育館&gt;', html)
        self.assertIn('見つかりました: 1 件', html)

    def test_search_returns_explicit_zero_result_page(self):
        response = self.client.get('/search_results?name=存在しない')
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn('見つかりました: 0 件', html)
        self.assertIn('検索条件を満たす避難所がありません。', html)


if __name__ == '__main__':
    unittest.main()