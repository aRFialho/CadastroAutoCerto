# SQL oficial do Robô Athos (Firebird)
# - NÃO filtra por Grupo3
# - Mantém cálculo de ESTOQUE_REAL_KIT por componente (MIN dos kits possíveis)

ATHOS_SQL_QUERY = r"""
WITH reserva AS (
  SELECT
    pr.codprod,
    SUM(COALESCE(pr.qtdepedido, 0)) AS qtde_reservada
  FROM produto_reserva pr
  GROUP BY pr.codprod
),

base_kit AS (
  SELECT
    pk.codprod AS CODIGO_KIT,
    pk.codbarra AS CODBARRA_KIT,
    c.codprod AS CODIGO_COMPONENTE,
    k.qtde AS QTDE_NO_KIT,

    CAST(REPLACE(TRIM(COALESCE(c.estatual, '0')), ',', '.') AS NUMERIC(18,4))
      - COALESCE(r.qtde_reservada, 0) AS EST_DISPONIVEL,

    CASE
      WHEN COALESCE(k.qtde, 0) <= 0 THEN 0
      WHEN (
        CAST(REPLACE(TRIM(COALESCE(c.estatual, '0')), ',', '.') AS NUMERIC(18,4))
        - COALESCE(r.qtde_reservada, 0)
      ) < 1 THEN 0
      ELSE CAST(
        TRUNC(
          (
            CAST(REPLACE(TRIM(COALESCE(c.estatual, '0')), ',', '.') AS NUMERIC(18,4))
            - COALESCE(r.qtde_reservada, 0)
          ) / k.qtde
        ) AS INTEGER
      )
    END AS KITS_POSSIVEIS_COMPONENTE
  FROM kitprodutos k
  INNER JOIN produto pk ON pk.codprod = k.codigo
  INNER JOIN produto c ON c.codprod = k.produto
  LEFT JOIN reserva r ON r.codprod = c.codprod
  WHERE pk.inativo = 'F'
),

estoque_kit AS (
  SELECT
    CODBARRA_KIT,
    MIN(KITS_POSSIVEIS_COMPONENTE) AS ESTOQUE_REAL_KIT
  FROM base_kit
  GROUP BY CODBARRA_KIT
)

SELECT
  -- 🔶 PRODUTO ACABADO (PA)
  pa.codbarra              AS CODBARRA_PRODUTO,
  pa.codauxiliar           AS CODAUXILIAR_PRODUTO,
  pa.observacao            AS COMPLEMENTO_PRODUTO,
  CAST(REPLACE(TRIM(COALESCE(pa.estatual, '0')), ',', '.') AS NUMERIC(18,4)) AS ESTOQUE_REAL_PRODUTO,
  pa.site_disponibilidade  AS PRAZO_PRODUTO,
  fpa.descrfabricante      AS FABRICANTE_PRODUTO,
  g3pa.descricao           AS NOME_GRUPO3,
  gpa.descricao            AS NOME_GRUPO,

  -- 🔷 KIT
  kit.codbarra             AS CODBARRA_KIT,
  kit.codauxiliar          AS CODAUXILIAR_KIT,
  kit.observacao           AS COMPLEMENTO_KIT,
  kit.site_disponibilidade AS PRAZO_KIT,
  fkit.descrfabricante     AS FABRICANTE_KIT,
  COALESCE(ek.ESTOQUE_REAL_KIT, 0) AS ESTOQUE_REAL_KIT,
  gkit.descricao           AS NOME_GRUPO_KIT,

  -- 🔵 PAI DO KIT
  pai.codbarra             AS CODBARRA_PAI,
  pai.codauxiliar          AS CODAUXILIAR_PAI,
  pai.observacao           AS COMPLEMENTO_PAI,
  pai.site_disponibilidade AS PRAZO_PAI,
  fpai.descrfabricante     AS FABRICANTE_PAI,
  gpai.descricao           AS NOME_GRUPO_PAI

FROM produto pa

-- Grupo3 do PA (SEM filtro)
LEFT JOIN grupo3 g3pa
  ON g3pa.codigo = pa.grupo3

-- Grupo (normal) do PA
LEFT JOIN grupo gpa
  ON gpa.codigo = pa.grupo

LEFT JOIN fabricante fpa
  ON fpa.fabricante = pa.fabricante

-- relação PA -> KIT
LEFT JOIN kitprodutos kp
  ON kp.produto = pa.codprod

LEFT JOIN produto kit
  ON kit.codprod = kp.codigo
  AND kit.inativo = 'F'

LEFT JOIN estoque_kit ek
  ON ek.CODBARRA_KIT = kit.codbarra

LEFT JOIN fabricante fkit
  ON fkit.fabricante = kit.fabricante

-- Grupo (normal) do KIT
LEFT JOIN grupo gkit
  ON gkit.codigo = kit.grupo

-- relação KIT -> PAI
LEFT JOIN produtopaifilho ppf
  ON ppf.codprodfilho = kit.codprod

LEFT JOIN produto pai
  ON pai.codprod = ppf.codprodpai
  AND pai.inativo = 'F'

LEFT JOIN fabricante fpai
  ON fpai.fabricante = pai.fabricante

-- Grupo (normal) do PAI
LEFT JOIN grupo gpai
  ON gpai.codigo = pai.grupo

WHERE
  pa.inativo = 'F'

ORDER BY
  pa.codbarra,
  kit.codbarra
"""
