"""
Todo print citado na aba Manual existe em manual/prints/.

    python -m unittest discover -s tests -t .
"""

import pathlib
import re
import unittest

from pluvio.abas.manual import PASTA_PRINTS


class TestManual(unittest.TestCase):

    def test_prints_existem(self):
        codigo = (pathlib.Path(__file__).resolve().parent.parent / "pluvio" / "abas" / "manual.py").read_text(encoding="utf-8")
        nomes = re.findall(r'tela\("([^"]+)"', codigo)

        self.assertTrue(nomes)

        for nome in nomes:
            self.assertTrue((PASTA_PRINTS / nome).exists(), nome)


if __name__ == "__main__":
    unittest.main()
