import re

import requests


def _tokenize(text: str) -> set:
    return {token for token in re.findall(r"[a-zA-Z0-9+#.]+", text.lower()) if len(token) > 2}


def local_screen(candidate_profile: dict, job: dict) -> dict:
    candidate_text = " ".join(
        [
            str(candidate_profile.get("cover_letter") or ""),
            str(candidate_profile.get("resume_text") or ""),
            " ".join(candidate_profile.get("skills") or []),
        ]
    )
    job_text = " ".join(
        [
            str(job.get("title") or ""),
            str(job.get("description") or ""),
            str(job.get("requirements") or ""),
        ]
    )

    candidate_tokens = _tokenize(candidate_text)
    job_tokens = _tokenize(job_text)

    if not job_tokens:
        return {"score": 0, "summary": "No job requirements provided", "source": "local"}

    overlap = candidate_tokens.intersection(job_tokens)
    ratio = len(overlap) / max(len(job_tokens), 1)
    score = round(min(95.0, 35 + ratio * 65), 2)

    return {
        "score": score,
        "summary": f"Matched {len(overlap)} keywords from job profile",
        "matched_keywords": sorted(list(overlap))[:20],
        "source": "local",
    }


def remote_screen(api_url: str, api_key: str, payload: dict, timeout_seconds: int) -> dict:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    response = requests.post(api_url, headers=headers, json=payload, timeout=timeout_seconds)
    response.raise_for_status()
    data = response.json()
    data["source"] = "remote"
    return data


def local_rank_potential_candidates(job: dict, candidates: list) -> dict:
    ranked = []
    for candidate in candidates:
        result = local_screen(candidate_profile=candidate, job=job)
        ranked.append(
            {
                "candidate": candidate,
                "score": result.get("score", 0),
                "summary": result.get("summary"),
                "source": result.get("source", "local"),
            }
        )

    ranked.sort(key=lambda item: item["score"], reverse=True)
    return {"candidates": ranked}


def remote_rank_potential_candidates(api_url: str, api_key: str, payload: dict, timeout_seconds: int) -> dict:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    response = requests.post(api_url, headers=headers, json=payload, timeout=timeout_seconds)
    response.raise_for_status()
    data = response.json()
    data["source"] = "remote"
    return data
