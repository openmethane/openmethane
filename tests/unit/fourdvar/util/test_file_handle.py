from fourdvar.util import file_handle


def test_load_and_unload(tmp_path):
    out_file = tmp_path / "test.pkl.gz"
    file_handle.save_list(["test"], out_file)
    assert file_handle.load_list(out_file) == ["test"]

    assert out_file.exists()
