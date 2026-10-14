"""
Componentes animados: pluviômetro, chuva e torneira.

Cada um é um arquivo .html em componentes/, com JavaScript simples e
sem etapa de build. Este módulo junta o CSS e o desenho do instrumento
comuns, injeta os números em JSON e mostra com st.iframe (que
substituiu st.components.v1.html). O HTML é sempre o destes arquivos;
os dados entram só como JSON.

Por que SVG + Canvas num componente HTML: o SVG desenha a geometria do
cone exata e nítida na TV do laboratório e no celular; o Canvas dá
conta de centenas de pingos; e quem mantém abre o arquivo e lê.
"""

import functools
import json
import pathlib

import streamlit as st


PASTA = pathlib.Path(__file__).resolve().parent.parent / "componentes"


@functools.lru_cache(maxsize=None)
def _ler(nome):
    return (PASTA / nome).read_text(encoding="utf-8")


def montar_html(nome, dados):
    """HTML final de um componente, com CSS, instrumento e dados."""

    dados_json = json.dumps(dados, ensure_ascii=False, default=str).replace("</", "<\\/")

    return (
        _ler(nome)
        .replace("/*__CSS__*/", _ler("base.css"))
        .replace("/*__INSTRUMENTO__*/", _ler("instrumento.js"))
        .replace("__DADOS__", dados_json)
    )


def tema():
    """'light' ou 'dark', conforme o tema em uso no Streamlit."""

    try:
        return st.context.theme.type or "light"
    except Exception:
        return "light"


def pluviometro(dados, altura="content"):
    st.iframe(montar_html("pluviometro.html", {**dados, "tema": tema()}), height=altura)


def chuva(dados, altura="content"):
    st.iframe(montar_html("chuva.html", {**dados, "tema": tema()}), height=altura)


def valvula(dados, altura="content"):
    st.iframe(montar_html("valvula.html", {**dados, "tema": tema()}), height=altura)
