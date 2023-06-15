import logging
import json
import os
import unittest
from unittest.mock import MagicMock, patch

import httpx
from dotenv import load_dotenv

from data import Course, ExternalTool, ExternalToolTab, ToolMigration
from exceptions import ConfigException, InvalidToolIdsException
from main import main, find_tools_for_migrations
from manager import API, AccountManager, CourseManager
from utils import convert_csv_to_int_list, find_entity_by_id, chunk_integer


logger = logging.getLogger(__name__)


class APITestCase(unittest.TestCase):
    """
    Integration/unit tests for API class
    """

    def setUp(self) -> None:
        self.api_url: str = os.getenv('API_URL', '')
        api_key: str = os.getenv('API_KEY', '')
        self.api = API(self.api_url, api_key)
        self.account_id = int(os.getenv('ACCOUNT_ID', 0))

        self.course_url = '/courses/11111111/'
        self.course_data = [{"name": "Test Course"}]

    def test_get_next_page_params_with_no_next_page(self):
        mock_response = MagicMock(httpx.Response)
        mock_response.links = {
            'next': {
                'url': f'{self.api_url}/api/v1/accounts/{self.account_id}/courses/?page=2&per_page=5',
                'rel': 'next'
            }
        }
        params = API.get_next_page_params(mock_response)
        self.assertEqual(params, { 'page': ['2'], 'per_page': ['5'] })

    def test_get_results_from_pages(self):
        with self.api.client:
            results = self.api.get_results_from_pages(f'/accounts/{self.account_id}/courses', page_size=5)
        self.assertTrue(len(results) > 1)

    def test_get_results_from_pages_with_limit(self):
        with self.api.client:
            results = self.api.get_results_from_pages(f'/accounts/{self.account_id}/courses', page_size=5, limit=2)
        self.assertTrue(len(results) == 2)

    def test_get_retries_on_http_error(self):
        expected_result = self.course_data
        request = MagicMock(httpx.Request, autospec=True, url=self.course_url)
        resp = httpx.Response(
            status_code=httpx.codes.BAD_GATEWAY,
            request=request
        )
        expected_resp = httpx.Response(
            status_code=httpx.codes.OK,
            request=request,
            text=json.dumps(expected_result)
        )

        with patch.object(self.api.client, 'get', autospec=True) as mock_get_call:
            mock_get_call.side_effect = [resp, expected_resp]
            with self.api.client:
                result = self.api.get(self.course_url)
        self.assertEqual(mock_get_call.call_count, 2)
        self.assertEqual(expected_result, result.data)

    def test_get_retries_on_decode_error(self):
        request = MagicMock(httpx.Request, autospec=True, url=self.course_url)
        bad_json_resp = httpx.Response(
            status_code=httpx.codes.OK,
            request=MagicMock(spec=httpx.Request),
            text=json.dumps(self.course_data)[:-3],
        )
        expected_resp = httpx.Response(
            status_code=httpx.codes.OK,
            request=request,
            text=json.dumps(self.course_data)
        )
        with patch.object(self.api.client, 'get', autospec=True) as mock_get_call:
            mock_get_call.side_effect = [bad_json_resp, expected_resp]
            with self.api.client:
                result = self.api.get(self.course_url)
        self.assertEqual(self.course_data, result.data)
        self.assertEqual(mock_get_call.call_count, 2)


class AccountManagerTestCase(unittest.TestCase):
    """
    Integration tests for AccountManager class
    """

    def setUp(self) -> None:
        api_url: str = os.getenv('API_URL', '')
        api_key: str = os.getenv('API_KEY', '')
        self.account_id = int(os.getenv('ACCOUNT_ID', 0))
        self.enrollment_term_ids: list[int] = convert_csv_to_int_list(os.getenv('ENROLLMENT_TERM_IDS', '0'))
        self.api = API(api_url, api_key)

    def test_manager_gets_tools(self):
        with self.api.client:
            manager = AccountManager(self.account_id, self.api)
            tools = manager.get_tools_installed_in_account()
        self.assertTrue(len(tools) > 0)
        for tool in tools:
            logger.debug(tool)
            self.assertTrue(isinstance(tool, ExternalTool))

    def test_manager_get_courses_in_single_term(self):
        with self.api.client:
            manager = AccountManager(self.account_id, self.api)
            courses = manager.get_courses_in_terms([self.enrollment_term_ids[0]], 150)
        self.assertTrue(len(courses) > 0)
        term_ids: list[int] = []
        for course in courses:
            self.assertTrue(isinstance(course, Course))
            term_ids.append(course.enrollment_term_id)
        term_id_set = set(term_ids)
        self.assertTrue(len(term_id_set) == 1)

    def test_manager_get_courses_in_multiple_terms(self):
        with self.api.client:
            manager = AccountManager(self.account_id, self.api)
            courses = manager.get_courses_in_terms(self.enrollment_term_ids, 150)
        self.assertTrue(len(courses) > 0)
        term_ids: list[int] = []
        for course in courses:
            self.assertTrue(isinstance(course, Course))
            term_ids.append(course.enrollment_term_id)
        term_id_set = set(term_ids)
        self.assertTrue(len(term_id_set) > 1)

    def test_manager_get_courses_with_limit(self):
        with self.api.client:
            manager = AccountManager(self.account_id, self.api)
            courses = manager.get_courses_in_terms(self.enrollment_term_ids, 50)
        self.assertTrue(len(courses) > 0)
        for course in courses:
            self.assertTrue(isinstance(course, Course))
        self.assertTrue(len(courses) <= 50)


class CourseManagerTestCase(unittest.TestCase):
    """
    Integration/unit tests for CourseManager class
    """

    def setUp(self):
        api_url: str = os.getenv('API_URL', '')
        api_key: str = os.getenv('API_KEY', '')
        self.api = API(api_url, api_key)
        self.test_course_id: int = int(os.getenv('TEST_COURSE_ID', '0'))
        self.enrollment_term_id: int = int(os.getenv('ENROLLMENT_TERM_ID', '0'))
        self.course_manager = CourseManager(
            Course(self.test_course_id, name='Test Course', enrollment_term_id=self.enrollment_term_id),
            self.api
        )
        self.source_tool_id: int = int(os.getenv('SOURCE_TOOL_ID', '0'))
        self.target_tool_id: int = int(os.getenv('TARGET_TOOL_ID', '0'))

        self.test_external_tool_tab = ExternalToolTab(
            id='context_external_tool_99999',
            label='Test External Tool',
            tool_id=99999,
            is_hidden=True,
            position=30
        )

    def test_find_tab_by_tool_id_returns_tab(self):
        tab = CourseManager.find_tab_by_tool_id(99999, [self.test_external_tool_tab])
        self.assertTrue(isinstance(tab, ExternalToolTab))

    def test_find_tab_by_tool_id_returns_none(self):
        tab = CourseManager.find_tab_by_tool_id(100000, [self.test_external_tool_tab])
        self.assertTrue(tab is None)

    def test_manager_gets_tool_tabs_in_course(self):
        with self.api.client:
            tabs = self.course_manager.get_tool_tabs()
        self.assertTrue(len(tabs) > 0)
        for tab in tabs:
            self.assertTrue(isinstance(tab, ExternalToolTab))

    def test_update_tool_tab_with_position(self):
        with self.api.client:
            tabs = self.course_manager.get_tool_tabs()
            source_tab = CourseManager.find_tab_by_tool_id(self.source_tool_id, tabs)
            if source_tab is None:
                raise InvalidToolIdsException(f'Tool with ID {self.source_tool_id} is not available in this course')
            new_tab = self.course_manager.update_tool_tab(source_tab, is_hidden=not source_tab.is_hidden, position=5)
            self.assertNotEqual(new_tab.is_hidden, source_tab.is_hidden)
            self.assertEqual(new_tab.position, 5)

    def test_manager_replaces_tool_tab_in_course(self):
        with self.api.client:
            tabs_before = self.course_manager.get_tool_tabs()
            source_tab = CourseManager.find_tab_by_tool_id(self.source_tool_id, tabs_before)
            target_tab = CourseManager.find_tab_by_tool_id(self.target_tool_id, tabs_before)
            if source_tab is None or target_tab is None:
                raise Exception(
                    'One or both of the tools with these IDs are not available in this course: ' +
                    str([self.source_tool_id, self.target_tool_id])
                )
            source_original_position = source_tab.position

            self.course_manager.replace_tool_tab(source_tab, target_tab)
            tabs_after = self.course_manager.get_tool_tabs()

        source_tab = CourseManager.find_tab_by_tool_id(self.source_tool_id, tabs_after)
        target_tab = CourseManager.find_tab_by_tool_id(self.target_tool_id, tabs_after)
        if source_tab is not None and target_tab is not None:
            self.assertTrue(source_tab.is_hidden)
            self.assertFalse(target_tab.is_hidden)
            self.assertTrue(target_tab.position == source_original_position)


class UtilsTestCase(unittest.TestCase):
    """
    Unit tests for utils
    """

    def setUp(self):
        self.test_external_tool = ExternalTool(id=77777, name='Test External Tool')

    def test_find_tool_by_id_returns_tool(self):
        tool = find_entity_by_id(77777, [self.test_external_tool])
        self.assertTrue(isinstance(tool, ExternalTool))

    def test_find_tool_by_id_returns_none(self):
        tool = find_entity_by_id(77778, [self.test_external_tool])
        self.assertTrue(tool is None)

    def test_convert_csv_to_int_list_when_valid(self):
        int_list = convert_csv_to_int_list('6,7,8')
        for elem in int_list:
            self.assertIsInstance(elem, int)
        int_list = convert_csv_to_int_list('6')
        self.assertIsInstance(int_list[0], int)

    def test_convert_csv_to_int_list_when_invalid(self):
        with self.assertRaises(ConfigException):
            convert_csv_to_int_list('6,7,blahblah,8')
        with self.assertRaises(ConfigException):
            convert_csv_to_int_list(',')
        with self.assertRaises(ConfigException):
            convert_csv_to_int_list('')

    def test_chunk_integer(self):
        chunks = chunk_integer(150, 3)
        self.assertEqual(chunks, [50, 50, 50])
        chunks = chunk_integer(5, 2)
        self.assertEqual(chunks, [3, 2])
        chunks = chunk_integer(23, 5)
        self.assertEqual(chunks, [5, 5, 5, 4, 4])
        chunks = chunk_integer(14, 4)
        self.assertEqual(chunks, [4, 4, 3, 3])


class MainTestCase(unittest.TestCase):

    def setUp(self) -> None:
        api_url: str = os.getenv('API_URL', '')
        api_key: str = os.getenv('API_KEY', '')
        self.api = API(api_url, api_key)
        self.account_id: int = int(os.getenv('ACCOUNT_ID', '0'))
        self.enrollment_term_ids: list[int] = convert_csv_to_int_list(os.getenv('ENROLLMENT_TERM_IDS', '0'))

        self.source_tool_id: int = int(os.getenv('SOURCE_TOOL_ID', '0'))
        self.target_tool_id: int = int(os.getenv('TARGET_TOOL_ID', '0'))

    def test_find_tool_ids_for_migrations_raises_exception_when_tool_ids_are_invalid(self):
        with self.api.client:
            account_manager = AccountManager(self.account_id, self.api)
            tools = account_manager.get_tools_installed_in_account()
        with self.assertRaises(InvalidToolIdsException):
            find_tools_for_migrations(tools, [ToolMigration(100000000, 100000001)])

    def test_main_migrates_tool_successfully(self):
        main(
            self.api,
            self.account_id,
            self.enrollment_term_ids,
            [ToolMigration(source_id=self.source_tool_id, target_id=self.target_tool_id)]
        )
        # what needs to be checked?


if __name__ == '__main__':
    root_dir: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(root_dir, '.env'), verbose=True)

    log_level = os.getenv('LOG_LEVEL', 'INFO')
    http_log_level = os.getenv('HTTP_LOG_LEVEL', 'WARN')
    logging.basicConfig(level=log_level)

    httpx_logger = logging.getLogger('httpx')
    httpx_logger.setLevel(http_log_level)
    httpcore_level = logging.getLogger('httpcore')
    httpcore_level.setLevel(http_log_level)

    unittest.main()
