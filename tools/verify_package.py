"""Inspect portable package contents without extracting or running them."""
import io
import json
import zipfile
from pathlib import Path
from service.config import ROOT, CONFIG


def main():
    archive=ROOT/'dist/shared-ghidra-service.zip'
    with zipfile.ZipFile(archive) as z:
        names=z.namelist()
        assert {'README.md','LICENSE','pytest.ini','target/shared-service.jar'} <= set(names)
        assert not any(n.startswith(('.local/','runtime/','.venv/')) or '..' in Path(n).parts for n in names)
        forbidden=[]
        if CONFIG.exists():forbidden.append(json.loads(CONFIG.read_text())['token'].encode())
        for name in names:
            data=z.read(name)
            assert not any(token in data for token in forbidden),name
            if name.endswith('.py'):compile(data,name,'exec')
        with zipfile.ZipFile(io.BytesIO(z.read('target/shared-service.jar'))) as packaged:
            with zipfile.ZipFile(ROOT/'target/shared-service.jar') as built:
                assert set(packaged.namelist())==set(built.namelist())
                assert all(packaged.read(n)==built.read(n) for n in packaged.namelist())
            assert not any('GhidraMCPPlugin' in n for n in packaged.namelist())
    print(f'Package verified: {len(names)} files; source parses, engine matches build, no runtime state or token')


if __name__=='__main__':main()
