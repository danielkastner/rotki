import pytest

from rotkehlchen.tests.utils.exchanges import create_test_gate


@pytest.fixture(scope='function')
def function_scope_gate(
        database,
        inquirer,  # pylint: disable=unused-argument,
        function_scope_messages_aggregator,
):
    mock = create_test_gate(
        database=database,
        msg_aggregator=function_scope_messages_aggregator,
    )
    return mock
