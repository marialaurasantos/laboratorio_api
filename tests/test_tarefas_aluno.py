"""TAREFA DO ALUNO -- os cinco testes que faltam para os >= 8 do entregavel.

Cada teste abaixo tem nome, docstring e um pytest.skip. Apague o skip, escreva o
corpo, e o teste passa a valer. Nenhum deles precisa de banco: os tres primeiros
rodam so contra o motor.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_EVEN, localcontext

from app.dominio.motor_emergia import calcular_indices
from app.dominio.tipos import CategoriaFluxo, FluxoEmergetico


def test_regressao_numerica_contra_a_planilha(fluxos_golden):
    """Compara os seis indices com a aba SSB da Planilha_base.xlsx.

    Criterio do entregavel: abs(delta) <= 1E-6 por indice. Comece pelo inventario
    de referencia (Y = 200, F = 50, renovaveis = 115, nao renovaveis = 85) e
    escreva os seis valores esperados a mao antes de rodar -- se o teste passar
    de primeira sem voce saber o valor esperado, ele nao esta provando nada.
    """
    indices = calcular_indices(fluxos_golden, Decimal("1000"))

    assert indices.y == Decimal("200.000000")
    assert indices.eyr == Decimal("4.000000")
    assert indices.elr == Decimal("0.739130")
    assert indices.esi == Decimal("5.411765")
    assert indices.eii == Decimal("0.184783")
    assert indices.percentual_r == Decimal("57.500000")


def test_quantizacao_unica_no_final(fluxos_golden):
    """Mostra o erro duplo de arredondar no meio do calculo.

    Calcule ESI = EYR / ELR de duas formas: (a) quantizando EYR e ELR para seis
    casas antes de dividir; (b) dividindo em 28 digitos e quantizando so o ESI.
    Os dois resultados diferem -- e o motor usa (b). Prove a diferenca.
    """

    seis_casas = Decimal("1E-6")

    with localcontext() as ctx:
        ctx.prec = 28
        ctx.rounding = ROUND_HALF_EVEN

        eyr = Decimal("200") / Decimal("50")
        elr = Decimal("85") / Decimal("115")

        esi_com_arredondamento_intermediario = (
            eyr.quantize(seis_casas) / elr.quantize(seis_casas)
        ).quantize(seis_casas)

        esi_com_quantizacao_final = (eyr / elr).quantize(seis_casas)

    assert esi_com_arredondamento_intermediario == Decimal("5.411768")
    assert esi_com_quantizacao_final == Decimal("5.411765")
    assert esi_com_arredondamento_intermediario != esi_com_quantizacao_final

    indices = calcular_indices(fluxos_golden, Decimal("1000"))
    assert indices.esi == esi_com_quantizacao_final


def test_ordem_da_soma_com_magnitudes_divergentes():
    """A associatividade quebra quando as magnitudes divergem.

    Monte um inventario com um fluxo de 1E20 sej e outro de 1E-5 sej e some nas
    duas ordens possiveis. Explique, no corpo do teste, por que a precisao de 28
    digitos e o limite -- e por que ordenar o inventario e uma decisao de dominio.
    """

    grande = FluxoEmergetico("fluxo-grande", CategoriaFluxo.R, Decimal("1E20"))
    pequenos = [
        FluxoEmergetico(f"fluxo-pequeno-{i}", CategoriaFluxo.R, Decimal("1E-5"))
        for i in range(10)
    ]
    nao_renovavel = FluxoEmergetico(
        "recurso-nao-renovavel",
        CategoriaFluxo.N,
        Decimal("1E20"),
    )
    comprado = FluxoEmergetico(
        "material-comprado",
        CategoriaFluxo.MR,
        Decimal("1E20"),
    )

    # Com precisão insuficiente, a ordem da soma perde informação.
    with localcontext() as ctx:
        ctx.prec = 25

        grande_primeiro = sum(
            (fluxo.emergia_sej for fluxo in [grande, *pequenos]),
            Decimal("0"),
        )
        pequenos_primeiro = sum(
            (fluxo.emergia_sej for fluxo in [*pequenos, grande]),
            Decimal("0"),
        )

    assert grande_primeiro != pequenos_primeiro

    # O motor fixa 28 dígitos e, nesse inventário, preserva o resultado
    # mesmo quando os fluxos chegam em outra ordem.
    inventario_grande_primeiro = [
        grande,
        *pequenos,
        nao_renovavel,
        comprado,
    ]
    inventario_pequenos_primeiro = [
        *pequenos,
        grande,
        nao_renovavel,
        comprado,
    ]

    indices_grande_primeiro = calcular_indices(
        inventario_grande_primeiro,
        Decimal("1000"),
    )
    indices_pequenos_primeiro = calcular_indices(
        inventario_pequenos_primeiro,
        Decimal("1000"),
    )

    assert indices_grande_primeiro == indices_pequenos_primeiro


def test_erro_de_dominio_responde_problem_json(cliente, corpo_golden):
    """Inventario sem fluxo renovavel deve sair 422 em application/problem+json.

    Hoje sai 500, porque o handler de FluxosInsuficientes nao existe -- note que
    o 404 e o 422 do framework JA saem no formato certo, pelos handlers do
    esqueleto: o que falta e so o erro de dominio. Feche o TODO PASSO 3 em
    app/main.py e depois assegure aqui: status 422, header content-type
    application/problem+json e os cinco campos da RFC 9457.
    """

    corpo_golden["fluxos"] = [
        {"recurso": "solo", "categoria": "N", "emergia_sej": "50"},
        {"recurso": "diesel", "categoria": "MN", "emergia_sej": "20"},
    ]

    resposta = cliente.post("/v1/safras/42/calculos", json=corpo_golden)

    assert resposta.status_code == 422
    assert resposta.headers["content-type"].startswith("application/problem+json")

    corpo = resposta.json()
    assert corpo["type"] == "https://agroemergia.sc/erros/fluxos-insuficientes"
    assert corpo["status"] == 422

    for campo in ("type", "title", "status", "detail", "instance"):
        assert campo in corpo


def test_campo_extra_no_corpo_da_requisicao_e_rejeitado(cliente, corpo_golden):
    """"energia_produto_jj" tem de morrer com 422, nao virar calculo incompleto.

    Hoje o CalculoRequestDTO nao declara extra="forbid": o campo desconhecido e
    ignorado e o typo passa silencioso, exatamente como na planilha. Feche o
    TODO PASSO 3 em app/api/v1/dto.py e prove aqui.
    """

    corpo_golden["energia_produto_jj"] = "1000"

    resposta = cliente.post("/v1/safras/42/calculos", json=corpo_golden)

    assert resposta.status_code == 422
    assert resposta.headers["content-type"].startswith("application/problem+json")

    corpo = resposta.json()
    assert corpo["status"] == 422
    assert any(
        erro["campo"] == "body.energia_produto_jj"
        for erro in corpo["erros"]
    )
