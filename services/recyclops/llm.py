import json
import logging
import re
import os
from langchain_openai import ChatOpenAI
from models import InvokeRequest, AccessibilityReport
from prompt import ACCESSIBILITY_PROMPT

logger = logging.getLogger(__name__)


class CersIA:
    """
    Interface proprietária de invocação do LLM de acessibilidade.
    Uso: await CersIA.invoke(request)
    """

    _llm = None

    @classmethod
    def _get_llm(cls):
        """Inicializa o LLM de forma lazy para evitar problemas de start-up."""
        if cls._llm is None:
            logger.info("[CERS-IA] Inicializando ChatOpenAI com modelo gpt-4o-mini...")
            try:
                api_key = os.environ.get("OPENAI_API_KEY")
                if not api_key:
                    logger.error("[CERS-IA] OPENAI_API_KEY não está definida!")
                    raise ValueError("OPENAI_API_KEY não configurada")

                cls._llm = ChatOpenAI(
                    model="gpt-4o-mini", temperature=0, max_tokens=4096, api_key=api_key
                )
                logger.info("[CERS-IA] ChatOpenAI inicializado com sucesso")
            except Exception as e:
                logger.error(
                    f"[CERS-IA] Erro ao inicializar ChatOpenAI: {e}", exc_info=True
                )
                raise
        return cls._llm

    @classmethod
    async def invoke(cls, request: InvokeRequest) -> AccessibilityReport:
        filename = request.pr_metadata.get("filename", "arquivo.html")
        logger.info(f"[CERS-IA] Analisando: {filename}")

        llm = cls._get_llm()
        chain = ACCESSIBILITY_PROMPT | llm

        result = await chain.ainvoke(
            {"html_content": request.html_content, "filename": filename}
        )

        raw = result.content.strip()
        raw = cls._clean_json_response(raw)

        try:
            data = json.loads(raw)
            report = AccessibilityReport(**data)
            logger.info(
                f"[CERS-IA] Score: {report.score}/100 | Issues: {len(report.issues)} | Arquivo: {filename}"
            )
            return report
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"[CERS-IA] Erro ao parsear resposta: {e}\nRaw: {raw}")
            # Retorna um report de erro para não travar o fluxo
            return AccessibilityReport(
                score=0,
                issues=[],
                suggestions=[],
                summary=f"Erro ao analisar o arquivo: {str(e)}",
            )

    @staticmethod
    def _clean_json_response(raw: str) -> str:
        """Remove markdown code blocks se o LLM os incluir mesmo instruído a não."""
        raw = re.sub(r"^```(?:json)?\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        return raw.strip()
