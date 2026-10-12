import users


def test_split_functions_exist_and_work():
    assert hasattr(users, "active_users")
    assert hasattr(users, "format_names")
    data = [
        {"name": "  ann ", "active": True},
        {"name": "bob", "active": False},
        {"name": "cid", "active": True},
    ]
    assert users.active_users(data) == [data[0], data[2]]
    assert users.format_names(data) == ["Ann", "Bob", "Cid"]


def test_process_delegates():
    data = [{"name": " ann ", "active": True}, {"name": "bob", "active": False}]
    assert users.process(data) == ["Ann"]
    assert users.process([]) == []
