import logging
import os
from contextlib import nullcontext

from dotenv import load_dotenv

from api import API
from data import ExternalTool, ToolMigration
from db import DB, Dialect
from exceptions import InvalidToolIdsException
from manager import AccountManagerFactory, CourseManager
from utils import convert_csv_to_int_list, find_entity_by_id


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


def main(api: API, account_id: int, term_ids: list[int], migrations: list[ToolMigration], db: DB | None = None):
    
    factory = AccountManagerFactory()
    account_manager = factory.get_manager(account_id, api, db)

    with api.client, db if db is not None else nullcontext():  # type: ignore
        tools = account_manager.get_tools_installed_in_account()
        tool_pairs = find_tools_for_migrations(tools, migrations)

        # get list of tools available in account
        courses = account_manager.get_courses_in_terms(term_ids)
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
    enrollment_term_ids: list[int] = convert_csv_to_int_list(os.getenv('ENROLLMENT_TERM_IDS', '0'))

    wh_host = os.getenv('WH_HOST')
    wh_port = os.getenv('WH_PORT')
    wh_name = os.getenv('WH_NAME')
    wh_user = os.getenv('WH_USER')
    wh_password = os.getenv('WH_PASSWORD')

    db: DB | None = None
    if (
        wh_host is not None and
        wh_port is not None and
        wh_name is not None and
        wh_user is not None and
        wh_password is not None
    ):
        logger.info('Warehouse connection is configured, so it will be used for some data fetching...')
        db = DB(
            Dialect.POSTGRES,
            {
                'host': wh_host,
                'port': wh_port,
                'name': wh_name,
                'user': wh_user,
                'password': wh_password
            }
        )

    source_tool_id: int = int(os.getenv('SOURCE_TOOL_ID', '0'))
    target_tool_id: int = int(os.getenv('TARGET_TOOL_ID', '0'))

    main(
        API(api_url, api_key),
        account_id,
        enrollment_term_ids,
        [ToolMigration(source_id=source_tool_id, target_id=target_tool_id)],
        db
    )
