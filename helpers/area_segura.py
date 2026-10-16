"""ÁREAS SEGURAS do vídeo vertical — onde a interface do Reels/TikTok/Shorts mora.

Regra do usuário (2026-10-13, medidas atualizadas no mesmo dia): em vídeo
vertical, NENHUM elemento nosso nas áreas da interface, salvo pedido explícito
dele (`forcarAreaInsegura: true` no edit-data do projeto). Em 1080×1920:

  * topo 250px — status, câmera, abas;
  * base 320px — perfil, botão seguir, texto do post, música;
  * laterais 120px de cada lado — a área útil é x = 120…960;
  * coluna dos ícones à direita (curtir, comentar, compartilhar): de x = 848
    até a borda útil, nos 768px de baixo (y ≥ 1152).

O VÍDEO pode ocupar essas áreas — a imagem atrás da interface é normal. Quem
não pode é o que a gente desenha: texto, legenda, cartão, ícone.
"""
from __future__ import annotations

REF_W, REF_H = 1080, 1920
TOPO, BASE, LATERAL = 250, 320, 120
ICONES_X, ICONES_Y0, ICONES_Y1 = 848, 1152, 1920
FOLGA = 10          # não encostar na linha


def vale(data: dict) -> bool:
    """Só no vertical 9:16, e só enquanto o usuário não forçou."""
    W, H = int(data.get("width", REF_W)), int(data.get("height", REF_H))
    return abs(W / H - 9 / 16) < 0.02 and not data.get("forcarAreaInsegura")


def topo_minimo(H: int = REF_H) -> float:
    return (TOPO + FOLGA) * H / REF_H


def base_minima(H: int = REF_H) -> float:
    """Menor distância do fundo do quadro até o pé de um elemento."""
    return (BASE + FOLGA) * H / REF_H


def lateral_minima(W: int = REF_W) -> float:
    """Menor distância da borda lateral até o TEXTO. O Reels no celular corta
    ~55px de cada lado (o 9:16 é escalado para encher a altura de uma tela mais
    estreita) — texto a 52px da borda saiu colado na borda no Instagram
    (2026-10-16, cartela notícia). Fundos e cartões podem sangrar; texto não."""
    return (LATERAL + FOLGA) * W / REF_W


def largura_util(W: int = REF_W) -> float:
    """Largura máxima de qualquer elemento centrado (fora da faixa dos ícones)."""
    return (REF_W - 2 * (LATERAL + FOLGA)) * W / REF_W


def largura_centrada_icones(W: int = REF_W) -> float:
    """Maior largura de algo CENTRADO que cabe à esquerda da coluna de ícones."""
    k = W / REF_W
    return 2 * (ICONES_X - FOLGA - REF_W / 2) * k


def na_faixa_dos_icones(y0: float, y1: float, H: int = REF_H) -> bool:
    k = H / REF_H
    return y1 > ICONES_Y0 * k and y0 < ICONES_Y1 * k
