import logging
import os

from dotenv import load_dotenv

from api import API
from data import ExternalTool, ToolMigration
from exceptions import InvalidToolIdsException
from manager import AccountManager, CourseManager
from utils import find_entity_by_id


logger = logging.getLogger(__name__)


def find_tools_for_migrations(
    tools: list[ExternalTool], migrations: list[ToolMigration]
) -> list[tuple[ExternalTool, ExternalTool]]:
    tool_pairs: list[tuple[ExternalTool, ExternalTool]] = []
    for migration in migrations:
        source_tool = find_entity_by_id(migration.source_id, tools)
        target_tool = find_entity_by_id(migration.target_id, tools)
        if source_tool is None or target_tool is None:
            invalid_tool_ids = []
            if source_tool is None:
                invalid_tool_ids.append(migration.source_id)
            if target_tool is None:
                invalid_tool_ids.append(migration.target_id)
            raise InvalidToolIdsException(
                'The following tool IDs from one of your migrations were not found in the account: ' +
                str(invalid_tool_ids)
            )
        tool_pairs.append((source_tool, target_tool))
    return tool_pairs


def main(api: API, account_id: int, term_id: int, migrations: list[ToolMigration]):
    account_manager = AccountManager(account_id, api)
    
    with api.client:
        tools = account_manager.get_tools_installed_in_account()
        tool_pairs = find_tools_for_migrations(tools, migrations)

        # get list of tools available in account
        courses = account_manager.get_courses_in_account_for_term(term_id)
        logger.info(f'Number of tools found in account {account_id}: {len(tools)}')

        for source_tool, target_tool in tool_pairs:
            logger.info(f'Source tool: {source_tool}')
            logger.info(f'Target tool: {target_tool}')

            for course in courses:
                # Replace target tool with source tool in course navigation
                course_manager = CourseManager(course, api)
                tabs = course_manager.get_tool_tabs()
                source_tool_tab = CourseManager.find_tab_by_tool_id(source_tool.id, tabs)
                target_tool_tab = CourseManager.find_tab_by_tool_id(target_tool.id, tabs)
                if source_tool_tab is None or target_tool_tab is None:
                    raise InvalidToolIdsException(
                        'One or both of the following tool IDs are not available in this course: ' + 
                        str([source_tool.id, target_tool.id])
                    )
                course_manager.replace_tool_tab(source_tool_tab, target_tool_tab)


if __name__ == '__main__':
    # get configuration (either env. variables, cli flags, or direct input)

    root_dir: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(root_dir, '.env'), verbose=True)

    # Set up logging
    log_level = os.getenv('LOG_LEVEL', 'INFO')
    http_log_level = os.getenv('HTTP_LOG_LEVEL', 'WARN')
    logging.basicConfig(level=log_level)

    httpx_logger = logging.getLogger('httpx')
    httpx_logger.setLevel(http_log_level)
    httpcore_level = logging.getLogger('httpcore')
    httpcore_level.setLevel(http_log_level)

    api_url: str = os.getenv('API_URL', '')
    api_key: str = os.getenv('API_KEY', '')
    account_id: int = int(os.getenv('ACCOUNT_ID', '0'))
    enrollment_term_id:  int = int(os.getenv('ENROLLMENT_TERM_ID', '0'))

    source_tool_id: int = int(os.getenv('SOURCE_TOOL_ID', '0'))
    target_tool_id: int = int(os.getenv('TARGET_TOOL_ID', '0'))

    main(
        API(api_url, api_key),
        account_id,
        enrollment_term_id,
        [ToolMigration(source_id=source_tool_id, target_id=target_tool_id)]
    )
