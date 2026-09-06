import requests
import re
from flask import current_app
from utils.embedding import VectorStoreManager

class RAGEngine:
    def __init__(self):
        self.vector_store = VectorStoreManager()
    def query_ollama(
        self,
        prompt: str,
        model: str = None,
        num_predict: int = 450
    ) -> str:

        base_url = current_app.config.get(
           "OLLAMA_BASE_URL",
           "http://localhost:11434"
        )

        selected_model = model or current_app.config.get(
            "DEFAULT_MODEL",
            "qwen2.5-coder:7b"
        )

        url = f"{base_url.rstrip('/')}/api/generate"

        payload = {
            "model": selected_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": num_predict,
                "temperature": 0.2
            }
        }

        print("\n========== OLLAMA REQUEST ==========")
        print("URL:", url)
        print("MODEL:", selected_model)
        print("PROMPT LENGTH:", len(prompt))
        print("MAX TOKENS:", num_predict)
        print("====================================")

        try:
            response = requests.post(
            url,
            json=payload,
            timeout=600
            )

            print("\n========== OLLAMA RESPONSE ==========")
            print("HTTP STATUS:", response.status_code)

            if response.status_code == 200:

                data = response.json()

                ollama_response = data.get("response", "").strip()

                print("RESPONSE LENGTH:", len(ollama_response))
                print("OLLAMA SUCCESS")
                print("=====================================\n")

                if ollama_response:
                    return ollama_response

                return self.generate_fallback_response(
                    prompt,
                    "Ollama returned an empty response"
                )

            print("OLLAMA ERROR:", response.text[:1000])
            print("=====================================\n")

            return self.generate_fallback_response(
                prompt,
                f"Ollama HTTP {response.status_code}"
            )

        except requests.exceptions.Timeout:
            print("\nOLLAMA TIMEOUT")
            print("Ollama took longer than 300 seconds.")
            print("=====================================\n")

            return self.generate_fallback_response(
                prompt,
                "Ollama request timed out after 300 seconds"
            )

        except requests.exceptions.ConnectionError as e:
            print("\nOLLAMA CONNECTION ERROR")
            print(str(e))
            print("=====================================\n")

            return self.generate_fallback_response(
                prompt,
                f"Ollama connection error: {str(e)}"
            )

        except Exception as e:
            print("\nOLLAMA UNEXPECTED ERROR")
            print(type(e).__name__)
            print(str(e))
            print("=====================================\n")

            return self.generate_fallback_response(
                prompt,
                f"{type(e).__name__}: {str(e)}"
            )
        
    def generate_fallback_response(self, prompt: str, error_msg: str) -> str:
        """
        Generates a highly structured, logical response using the provided prompt context
        if Ollama is offline or unavailable.
        """
        # Attempt to extract context and question from prompt
        context_match = re.search(r"Context:\s*(.*?)\s*Question:", prompt, re.DOTALL | re.IGNORECASE)
        question_match = re.search(r"Question:\s*(.*?)\s*Answer:", prompt, re.DOTALL | re.IGNORECASE)
        
        context_text = context_match.group(1).strip() if context_match else ""
        question = question_match.group(1).strip() if question_match else ""
        
        # If this is not a RAG question but a summarization request, parse that
        is_summarize = "summarize" in prompt.lower() or "summary" in prompt.lower()
        is_methodology = "methodology" in prompt.lower()
        is_results = "results" in prompt.lower() or "findings" in prompt.lower()
        is_conclusion = "conclusion" in prompt.lower()
        is_hypothesis = "hypothesis" in prompt.lower() or "hypotheses" in prompt.lower()

        fallback_prefix = f"*[Note: Using Local AI Fallback Engine because Ollama is offline or unreachable ({error_msg})]*\n\n"

        if is_hypothesis:
            # Generate hypothesis response
            return fallback_prefix + self._create_fallback_hypothesis(context_text, prompt)

        if is_summarize or is_methodology or is_results or is_conclusion:
            return fallback_prefix + self._create_fallback_analysis(context_text, is_summarize, is_methodology, is_results, is_conclusion)

        if not context_text:
            return fallback_prefix + f"I am ready to assist you. However, there is no uploaded paper context in my database. Please upload scientific papers (.pdf) first and select them to perform RAG inquiries.\n\nYour Question: **{question if question else 'N/A'}**"

        # Answer question using context
        sentences = re.split(r'(?<=[.!?])\s+', context_text)
        relevant_sentences = []
        
        # Clean question words to match sentences
        q_words = [w.lower() for w in re.findall(r'\w+', question) if len(w) > 3]
        for sentence in sentences:
            sentence_clean = sentence.lower()
            match_count = sum(1 for qw in q_words if qw in sentence_clean)
            if match_count > 0:
                relevant_sentences.append((match_count, sentence.strip()))
        
        relevant_sentences.sort(key=lambda x: x[0], reverse=True)
        top_sentences = [s[1] for s in relevant_sentences[:5]]
        
        if not top_sentences:
            top_sentences = [s.strip() for s in sentences[:3]]

        response_body = f"Based on the analyzed scientific literature, here are the findings regarding **\"{question}\"**:\n\n"
        for i, sent in enumerate(top_sentences, 1):
            # Clean up double spaces or linebreaks
            sent_cleaned = re.sub(r'\s+', ' ', sent)
            response_body += f"{i}. **Key Insight**: {sent_cleaned}\n"
            
        response_body += "\n### Synthesis & Discussion\n"
        response_body += f"The documents indicate that the research addresses elements related to your query. Specifically, they highlight parameters involving "
        response_body += ", ".join(q_words[:4]) if q_words else "the target variables"
        response_body += ". Further analysis of the methodology is suggested to validate these claims."
        
        return fallback_prefix + response_body
             
    def _create_fallback_analysis(
        self,
        context_text: str,
        is_summarize: bool = False,
        is_methodology: bool = False,
        is_results: bool = False,
        is_conclusion: bool = False
    ) -> str:
        """
        Literature-grounded fallback analysis.

        Uses only retrieved literature context.
        Does not invent numerical results or scientific claims.
        """

        context_text = (context_text or "").strip()

        if not context_text:
            return (
                "The provided literature does not contain enough retrieved "
                "context to perform this analysis."
            )

        sentences = re.split(
            r'(?<=[.!?])\s+',
            context_text
        )

        sentences = [
            re.sub(r'\s+', ' ', sentence).strip()
            for sentence in sentences
            if sentence.strip()
        ]

        evidence = sentences[:8]

        if is_methodology:
            heading = "### Methodology"
            intro = (
                "The retrieved literature describes the following "
                "methodological information:"
            )
        elif is_results:
            heading = "### Results"
            intro = (
                "The retrieved literature reports the following "
                "findings and results:"
            )
        elif is_conclusion:
            heading = "### Conclusion"
            intro = (
                "The retrieved literature supports the following "
                "conclusions:"
            )
        else:
            heading = "### Summary"
            intro = (
                "The retrieved literature provides the following "
                "evidence-based summary:"
            )

        response = f"{heading}\n\n{intro}\n\n"

        for i, sentence in enumerate(evidence, 1):
            response += f"{i}. {sentence}\n"

        response += (
            "\n\nThe analysis above is based only on the retrieved "
            "literature context. No unsupported numerical results, "
            "methods, or scientific claims have been added."
        )

        return response

    def _create_fallback_hypothesis(self, context_text: str, prompt: str) -> str:
        """
        Literature-grounded fallback hypothesis generator.

        IMPORTANT:
        This fallback does not invent algorithms, percentages,
        datasets, or scientific claims that are not present
        in the retrieved literature context.
        """

        # -----------------------------------------
        # Extract domain
        # -----------------------------------------
        domain = "Scientific Research"

        domain_match = re.search(
            r"DOMAIN:\s*(.*?)(?:\n|$)",
            prompt,
            re.IGNORECASE
        )

        if domain_match:
            domain = domain_match.group(1).strip()

        # -----------------------------------------
        # Clean context
        # -----------------------------------------
        context_text = (context_text or "").strip()

        if not context_text:
            return f"""### Summary

    The selected literature does not provide enough retrieved context to formulate a literature-grounded hypothesis in the domain of **{domain}**.

    ### Theoretical Rationale

    The provided literature context is empty, so a specific research gap cannot be established.
 
    ### Core Hypothesis

    The provided literature does not establish a sufficiently specific hypothesis.

    ### Methodology

    Additional relevant literature must be retrieved before a testable methodology can be proposed.

    ### Expected Outcomes

    No evidence-based expected outcome can be specified from the available context.
    """

        # -----------------------------------------
        # Extract useful sentences
        # -----------------------------------------
        sentences = re.split(
            r'(?<=[.!?])\s+',
            context_text
        )

        sentences = [
            re.sub(r'\s+', ' ', s).strip()
            for s in sentences
            if s.strip()
        ]

        # Use only retrieved literature
        evidence = sentences[:6]

        # -----------------------------------------
        # Detect possible limitation/gap sentences
        # -----------------------------------------
        gap_keywords = [
            "limitation",
            "challenge",
            "future work",
            "future research",
            "however",
            "remains",
            "lack",
            "difficult",
            "scalability",
            "bias",
            "problem",
            "gap"
        ]

        gap_sentences = []

        for sentence in sentences:
            sentence_lower = sentence.lower()

            if any(keyword in sentence_lower for keyword in gap_keywords):
                gap_sentences.append(sentence)

        # -----------------------------------------
        # Select evidence
        # -----------------------------------------
        if gap_sentences:
            rationale = gap_sentences[0]
        elif evidence:
            rationale = evidence[0]
        else:
            rationale = (
                "The provided literature contains insufficient evidence "
                "to identify a specific research limitation."
            )

        # -----------------------------------------
        # Build a SAFE hypothesis
        # -----------------------------------------
        if len(evidence) >= 2:
            evidence_1 = evidence[0]
            evidence_2 = evidence[1]
        else:
            evidence_1 = evidence[0] if evidence else ""
            evidence_2 = ""

        return f"""### Summary

    The selected literature provides evidence related to **{domain}** and identifies areas that require further investigation. A potential research direction is to investigate whether addressing the limitations identified in the literature can improve the effectiveness or applicability of the studied approach.

    ### Theoretical Rationale

    The retrieved literature states:

    > {rationale}

    This provides a literature-supported basis for investigating the identified limitation further. No specific numerical improvement or new algorithm is claimed because such evidence is not established by the retrieved context.

    ### Core Hypothesis

    A testable hypothesis is that addressing the limitation identified in the selected literature will produce measurable differences in the relevant evaluation outcomes compared with the existing approach.

    ### Methodology

    1. Use the same type of data or evaluation setting described in the selected literature.
    2. Implement the baseline approach reported in the literature.
    3. Implement the proposed modification addressing the identified limitation.
    4. Evaluate both approaches using the evaluation criteria reported in the literature.
    5. Compare the observed results.
    6. Repeat the evaluation using appropriate control conditions to determine whether the observed difference is reproducible.

    ### Expected Outcomes

    The hypothesis would be supported if the proposed modification produces a measurable improvement in the evaluation criteria while addressing the limitation identified in the literature.

    The hypothesis would not be supported if the proposed modification produces no meaningful difference or performs worse than the baseline.

    ### Literature Evidence

    {evidence_1}

    {evidence_2}
    """
    def answer_question(self, question: str, paper_ids: list = None, model: str = "qwen2.5-coder:7b") -> str:
        context_chunks = self.vector_store.query_similar(question, top_k=3, paper_ids=paper_ids)
        context_text = "\n\n".join(context_chunks)
        
        prompt = f"""
        You are an expert AI research scientist. Answer the user's question based ONLY on the provided context below.
        If the answer cannot be directly derived from the context, state that clearly.

        Context:
        {context_text}

        Question: {question}

        Answer:
        """
        return self.query_ollama(prompt, model=model)
    def generate_paper_summary(
    
        self, 
        paper_text: str, 
        task: str = "all",
        paper_ids: list = None
    ) -> dict:
        """
        Generate summary, methodology, results, and conclusion
        using relevant text from the paper.
        """

        # Keep the first part for the overall summary
        summary_text = paper_text[:800]

        # Retrieve relevant sections from the full paper
        methodology_chunks = self.vector_store.query_similar(
            "methodology experimental design methods algorithms techniques",
            top_k=2,
            paper_ids=paper_ids
        )

        results_chunks = self.vector_store.query_similar(
            "results findings experiments performance evaluation outcomes",
            top_k=2,
            paper_ids=paper_ids
        )

        conclusion_chunks = self.vector_store.query_similar(
            "conclusion discussion limitations future work research directions",
            top_k=2,
            paper_ids=paper_ids
        )

        methodology_text = "\n\n".join(methodology_chunks)
        results_text = "\n\n".join(results_chunks)
        conclusion_text = "\n\n".join(conclusion_chunks)

        prompt = f"""
    You are an expert scientific research assistant.

    Analyze the provided parts of a scientific paper.

    IMPORTANT:
    - Use ONLY the supplied paper text.
    - Do not invent information.
    - If a section is not supported by the supplied text, clearly say so.
    - Keep the response concise.

    ===== PAPER INTRODUCTION / SUMMARY =====
    {summary_text}

    ===== METHODOLOGY-RELATED TEXT =====
    {methodology_text}

    ===== RESULTS-RELATED TEXT =====
    {results_text}

    ===== CONCLUSION-RELATED TEXT =====
    {conclusion_text}

    Return exactly these four sections:

### Short Summary
Give 2-3 concise sentences.

### Methodology
Give 3-5 concise points based only on the supplied text.

### Results
Give 3-5 concise points based only on the supplied text.
Do not invent numerical results.

### Conclusion
Give 2-4 concise points based only on the supplied text.
    """

        raw_response = self.query_ollama(prompt,num_predict=500)

        short_summary = ""
        methodology = ""
        results = ""
        conclusion = ""

        # Short Summary
        match = re.search(
            r"### Short Summary\s*(.*?)(?=\n### Methodology|\Z)",
            raw_response,
            re.DOTALL | re.IGNORECASE
        )
        if match:
            short_summary = match.group(1).strip()

        # Methodology
        match = re.search(
            r"### Methodology\s*(.*?)(?=\n### Results|\Z)",
            raw_response,
            re.DOTALL | re.IGNORECASE
        )
        if match:
            methodology = match.group(1).strip()

        # Results
        match = re.search(
            r"### Results\s*(.*?)(?=\n### Conclusion|\Z)",
            raw_response,
            re.DOTALL | re.IGNORECASE
        )
        if match:
            results = match.group(1).strip()

        # Conclusion
        match = re.search(
            r"### Conclusion\s*(.*)",
            raw_response,
            re.DOTALL | re.IGNORECASE
        )
        if match:
            conclusion = match.group(1).strip()

        return {
            "short_summary": short_summary,
            "methodology": methodology,
            "results": results,
            "conclusion": conclusion
        }

    def generate_hypothesis(self, domain: str, paper_ids: list = None) -> dict:
        """
        Formulate a new scientific hypothesis using paper contexts.
        """
                # ==================================================
        # RETRIEVE EXISTING SELECTED PAPERS
        # ==================================================

        context_chunks = []

        if paper_ids:
            # Keep the existing literature retrieval unchanged.
            context_chunks = self.vector_store.query_similar(
                f"key contributions methodology findings limitations future work research gaps in {domain}",
                top_k=4,
                paper_ids=paper_ids
            )


        # ==================================================
        # RETRIEVE ADDITIONAL SCIFACT LITERATURE
        # ==================================================

        scifact_chunks = []

        try:
            client = self.vector_store.get_client()

            if not self.vector_store.use_fallback:

                collection = client.get_or_create_collection(
                    name="scientific_papers"
                )

                scifact_query = (
                    f"key contributions methodology findings limitations "
                    f"future work research gaps in {domain}"
                )

                query_embedding = self.vector_store.embeddings.embed_query(
                    scifact_query
                )

                scifact_results = collection.query(
                    query_embeddings=[query_embedding],
                    n_results=4,
                    where={"source": "scifact"}
                )

                if (
                    scifact_results
                    and scifact_results.get("documents")
                    and scifact_results["documents"][0]
                ):
                    scifact_chunks = scifact_results["documents"][0]

        except Exception as e:
            print(
                f"SciFact retrieval failed. "
                f"Continuing with existing literature: {e}"
            )


        # ==================================================
        # COMBINE LITERATURE SOURCES
        # ==================================================

        context_chunks = context_chunks + scifact_chunks

        context_text = "\n\n".join(context_chunks)
        
        prompt = f"""
        You are an AI scientific research assistant.

        Your task is to formulate ONE novel and testable research hypothesis
        based ONLY on the literature context provided below.

        DOMAIN:
        {domain}

        LITERATURE CONTEXT:
        {context_text}

        STRICT RULES:

        1. Use ONLY information supported by the literature context.
        2. Do NOT invent numerical improvements, percentages, datasets,
           algorithms, experiments, or performance claims.
        3. Do NOT introduce unrelated fields or technologies unless they
           are explicitly supported by the literature.
        4. Clearly distinguish existing findings from the proposed hypothesis.
        5. The hypothesis must address a research gap or limitation that is
           actually supported by the literature context.
        6. If the literature does not provide enough evidence for a specific
           claim, say "The provided literature does not establish this."
        7. Keep the hypothesis realistic and directly connected to the
           selected papers.
        8. Do not claim that something will improve by 25%, 30%, 50%, etc.
           unless that exact information appears in the literature context.

        RETURN EXACTLY THIS FORMAT:

        ### Summary
        Write 2-3 sentences explaining the research gap and the proposed
        research direction.

        ### Theoretical Rationale
        Explain which findings, limitations, or research gaps in the provided
        literature motivate the hypothesis.

        ### Core Hypothesis
        State ONE clear, testable hypothesis.

        ### Methodology
        Give 3-5 concise steps for testing the hypothesis.
        Use only methods supported by the literature.

        ### Expected Outcomes
        Give 2-4 concise points:
        - observations that would support the hypothesis
        - observations that would reject the hypothesis

        LITERATURE-BASED REQUIREMENT:

        Every important claim must be supported by the supplied literature.
        Do not fabricate evidence.
        """
        
        raw_response = self.query_ollama(prompt)
        print("\n========== HYPOTHESIS AI RESPONSE ==========")
        print(raw_response)
        print("============================================\n")
        
        # ==================================================
        # PARSE AI HYPOTHESIS RESPONSE
        # ==================================================

        clean_response = raw_response.strip()
        print("\n========== CLEAN HYPOTHESIS RESPONSE ==========")
        print(clean_response)
        print("===============================================\n")
        # Remove fallback notification if present
        clean_response = re.sub(
            r"\*\[Note:.*?\]\*",
            "",
            clean_response,
            flags=re.DOTALL | re.IGNORECASE
        ).strip()


        # ==================================================
        # TITLE
        # ==================================================

        title = f"Hypothesis for {domain}"

        # Try to extract a title if Ollama provides one
        title_match = re.search(
            r"(?:\*\*Title\*\*|###\s*Title|#\s*Hypothesis)\s*:?\s*(.*?)(?:\n|$)",
            clean_response,
            re.IGNORECASE
        )

        if title_match:
            title = title_match.group(1).strip()

        # Remove markdown formatting from title
        title = re.sub(r"[*#]", "", title).strip()


        # ==================================================
        # SUMMARY
        # ==================================================

        summary = "No summary was generated."

        summary_match = re.search(
            r"###\s*Summary\s*(.*?)(?=\n###\s|\Z)",
            clean_response,
            re.DOTALL | re.IGNORECASE
        )

        if summary_match:
            summary = summary_match.group(1).strip()


        # ==================================================
        # THEORETICAL RATIONALE
        # ==================================================

        description = "No theoretical rationale was generated."

        description_match = re.search(
          r"###\s*Theoretical\s+Rationale\s*(.*?)(?=\n###\s|\Z)",
          clean_response,
          re.DOTALL | re.IGNORECASE
        )

        if description_match:
            description = description_match.group(1).strip()


        # ==================================================
        # CORE HYPOTHESIS
        # ==================================================

        core_hypothesis = ""

        core_match = re.search(
            r"###\s*Core\s+Hypothesis\s*(.*?)(?=\n###\s|\Z)",
            clean_response,
            re.DOTALL | re.IGNORECASE
        )

        if core_match:
            core_hypothesis = core_match.group(1).strip()


        # ==================================================
        # METHODOLOGY
        #==================================================

        methodology = "No testing methodology was generated."

        methodology_match = re.search(
            r"###\s*Methodology\s*(.*?)(?=\n###\s|\Z)",
            clean_response,
            re.DOTALL | re.IGNORECASE
        )

        if methodology_match:
            methodology = methodology_match.group(1).strip()


        # ==================================================
        # EXPECTED OUTCOMES
        # ==================================================

        outcomes = "No expected outcomes were generated."

        outcomes_match = re.search(
            r"###\s*Expected\s+Outcomes\s*(.*?)(?=\n###\s|\Z)",
            clean_response,
            re.DOTALL | re.IGNORECASE
        )
 
        if outcomes_match:
            outcomes = outcomes_match.group(1).strip()


        # ==================================================
        # FALLBACK SUMMARY
        # ==================================================

        if summary == "No summary was generated.":

            if description != "No theoretical rationale was generated.":
                summary = description


        # ==================================================
        # FALLBACK DESCRIPTION
        # ==================================================

        if description == "No theoretical rationale was generated.":

            if core_hypothesis:
                description = core_hypothesis


        # ==================================================
        # GENERATE TITLE IF MODEL DID NOT PROVIDE ONE
        # ==================================================

        if title == f"Hypothesis for {domain}":

            if core_hypothesis:
                first_sentence = re.split(
                    r"(?<=[.!?])\s+",
                    core_hypothesis
                )[0].strip()

                title = first_sentence[:120]

                if len(first_sentence) > 120:
                    title += "..."

            else:
                title = f"Research Hypothesis for {domain}"

        # ==================================================
        # DEBUG OUTPUT
        # ==================================================

        print("\n========== PARSED HYPOTHESIS ==========")
        print("TITLE:", title)
        print("SUMMARY:", summary)
        print("DESCRIPTION:", description)
        print("CORE HYPOTHESIS:", core_hypothesis)
        print("METHODOLOGY:", methodology)
        print("OUTCOMES:", outcomes)
        print("=======================================\n")
        # Return structured data
        return {
            "title": title,
            "summary": summary,
            "description": description,
            "core_hypothesis": core_hypothesis,
            "methodology": methodology,
            "expected_outcomes": outcomes,
            "raw": raw_response
        }