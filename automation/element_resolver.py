"""Semantic element resolver with multi-signal ranking.

Resolves user intent (e.g., "click login button") to specific UI elements
using weighted signals: OCR similarity, UIA control type, bounding box,
and focus history.
"""

from __future__ import annotations

import difflib
from typing import List, Optional, Tuple

from awareness.perception_snapshot import PerceptionElement, PerceptionSnapshot


class ElementResolver:
    """Resolves semantic queries to UI elements using multi-signal ranking."""
    
    # Signal weights (must sum to 1.0)
    WEIGHT_OCR_SIMILARITY = 0.4
    WEIGHT_CONTROL_TYPE = 0.3
    WEIGHT_BBOX_SCORE = 0.2
    WEIGHT_FOCUS_HISTORY = 0.1
    
    def __init__(self):
        self._focus_history: List[str] = []  # Recent element texts that were focused
    
    def resolve(
        self,
        query: str,
        snapshot: PerceptionSnapshot,
        expected_type: Optional[str] = None
    ) -> Optional[PerceptionElement]:
        """Resolve a semantic query to the best matching element.
        
        Args:
            query: Natural language query (e.g., "login button", "search box")
            snapshot: Current perception snapshot
            expected_type: Optional expected element type filter
            
        Returns:
            Best matching element or None
        """
        candidates = snapshot.elements
        
        # Filter by expected type if provided
        if expected_type:
            candidates = [e for e in candidates if e.element_type == expected_type]
        
        if not candidates:
            return None
        
        # Score all candidates
        scored = []
        for elem in candidates:
            score = self._score_element(query, elem, snapshot)
            scored.append((score, elem))
        
        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)
        
        # Return best match if score is reasonable
        if scored and scored[0][0] > 0.3:
            return scored[0][1]
        
        return None
    
    def resolve_with_credentials(
        self,
        query: str,
        snapshot: PerceptionSnapshot
    ) -> dict:
        """PHASE 10: Resolve element with credential awareness.
        
        Detects password fields and auto-fills from vault.
        
        Args:
            query: Natural language query
            snapshot: Current perception snapshot
            
        Returns:
            Dict with element and action details (type_secret never logged)
        """
        elem = self.resolve(query, snapshot)
        
        if not elem:
            return {"element": None, "action": "click"}
        
        # PHASE 10: Detect password fields
        is_password = (
            elem.element_type in ("Edit", "Password", "PasswordBox") or
            "password" in elem.text.lower() or
            snapshot.browser.has_login_form
        )
        
        if is_password:
            try:
                from security.credential_vault import get_vault
                vault = get_vault()
                
                # Match login pattern from training
                vault_key = self._match_login_pattern(snapshot)
                
                if vault_key and vault.exists(vault_key):
                    # Return credential action (NEVER LOGGED)
                    return {
                        "element": elem,
                        "action": "type_secret",
                        "vault_key": vault_key,
                        "value": vault.get(vault_key),  # Retrieved but never logged
                    }
            except Exception:
                pass
        
        return {"element": elem, "action": "click"}
    
    def _match_login_pattern(self, snapshot: PerceptionSnapshot) -> Optional[str]:
        """Match current UI to trained login patterns.
        
        Args:
            snapshot: Current perception snapshot
            
        Returns:
            Vault key for credentials or None
        """
        # Check browser URL for known patterns
        if snapshot.browser.url:
            url_lower = snapshot.browser.url.lower()
            
            # Chrome profile login
            if "chrome" in url_lower or snapshot.active_app.lower() == "chrome.exe":
                # Look for profile name in UI elements
                for elem in snapshot.elements:
                    if elem.text and len(elem.text) > 3:
                        vault_key = f"chrome_profile_{elem.text}"
                        from security.credential_vault import get_vault
                        if get_vault().exists(vault_key):
                            return vault_key
                return "chrome_profile_Default"
            
            # WhatsApp unlock
            if "whatsapp" in url_lower or "whatsapp" in snapshot.active_window_title.lower():
                return "whatsapp_pin"
        
        return None
    
    def resolve_multiple(
        self,
        query: str,
        snapshot: PerceptionSnapshot,
        top_k: int = 5
    ) -> List[Tuple[float, PerceptionElement]]:
        """Resolve query to multiple ranked candidates.
        
        Args:
            query: Natural language query
            snapshot: Current perception snapshot
            top_k: Maximum number of results
            
        Returns:
            List of (score, element) tuples, sorted by score descending
        """
        candidates = snapshot.elements
        
        scored = []
        for elem in candidates:
            score = self._score_element(query, elem, snapshot)
            if score > 0.1:  # Minimum threshold
                scored.append((score, elem))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[:top_k]
    
    def _score_element(
        self,
        query: str,
        element: PerceptionElement,
        snapshot: PerceptionSnapshot
    ) -> float:
        """Compute weighted score for element match.
        
        Scoring algorithm:
        - OCR similarity: 0.4 weight (text match via difflib)
        - UIA control type: 0.3 weight (expected type match)
        - Bounding box: 0.2 weight (size and location)
        - Focus history: 0.1 weight (recently focused)
        
        Args:
            query: Search query
            element: Candidate element
            snapshot: Current snapshot
            
        Returns:
            Score from 0.0 to 1.0
        """
        score = 0.0
        
        # Signal 1: OCR/Text similarity (0.4 weight)
        text_score = self._compute_text_similarity(query, element.text)
        score += text_score * self.WEIGHT_OCR_SIMILARITY
        
        # Signal 2: Control type match (0.3 weight)
        type_score = self._compute_type_score(query, element.element_type)
        score += type_score * self.WEIGHT_CONTROL_TYPE
        
        # Signal 3: Bounding box score (0.2 weight)
        bbox_score = self._compute_bbox_score(element, snapshot)
        score += bbox_score * self.WEIGHT_BBOX_SCORE
        
        # Signal 4: Focus history (0.1 weight)
        focus_score = self._compute_focus_score(element)
        score += focus_score * self.WEIGHT_FOCUS_HISTORY
        
        return score
    
    def _compute_text_similarity(self, query: str, element_text: str) -> float:
        """Compute text similarity using fuzzy matching.
        
        Args:
            query: Search query
            element_text: Element text
            
        Returns:
            Similarity score 0.0-1.0
        """
        if not element_text:
            return 0.0
        
        query_lower = query.lower()
        text_lower = element_text.lower()
        
        # Exact match
        if query_lower == text_lower:
            return 1.0
        
        # Substring match
        if query_lower in text_lower:
            return 0.9
        
        # Word-level match
        query_words = set(query_lower.split())
        text_words = set(text_lower.split())
        
        if query_words and text_words:
            overlap = len(query_words & text_words)
            if overlap > 0:
                return 0.7 + (0.2 * overlap / len(query_words))
        
        # Fuzzy match using difflib
        ratio = difflib.SequenceMatcher(None, query_lower, text_lower).ratio()
        return ratio * 0.6  # Scale down fuzzy matches
    
    def _compute_type_score(self, query: str, element_type: str) -> float:
        """Score based on expected control type from query.
        
        Args:
            query: Search query
            element_type: Element control type
            
        Returns:
            Type match score 0.0-1.0
        """
        query_lower = query.lower()
        type_lower = element_type.lower()
        
        # Query hints for expected types
        type_hints = {
            "button": ["button", "btn"],
            "edit": ["input", "field", "box", "search", "text"],
            "link": ["link", "hyperlink"],
            "menuitem": ["menu", "option"],
            "checkbox": ["check", "checkbox"],
            "combobox": ["dropdown", "select", "combo"],
        }
        
        # Check if query suggests a specific type
        for expected_type, keywords in type_hints.items():
            if any(kw in query_lower for kw in keywords):
                if expected_type in type_lower:
                    return 1.0
                elif type_lower in expected_type:
                    return 0.8
        
        # Default: slight preference for interactive elements
        if type_lower in ("button", "link", "menuitem", "edit"):
            return 0.5
        
        return 0.3
    
    def _compute_bbox_score(
        self,
        element: PerceptionElement,
        snapshot: PerceptionSnapshot
    ) -> float:
        """Score based on bounding box size and location.
        
        Prefers:
        - Visible elements (has bounding box)
        - Reasonably sized elements (not too small/large)
        - Elements near center or top of screen
        
        Args:
            element: Candidate element
            snapshot: Current snapshot
            
        Returns:
            Bounding box score 0.0-1.0
        """
        if not element.bounding_box:
            return 0.0
        
        score = 0.5  # Base score for having a bbox
        
        # Size scoring
        area = element.area()
        if 100 < area < 50000:  # Reasonable size range
            score += 0.3
        elif area > 0:
            score += 0.1
        
        # Location scoring (prefer top half and center)
        center = element.center()
        if center:
            x, y = center
            # Prefer elements in top 60% of screen
            if y < 800:
                score += 0.1
            # Prefer elements not at extreme edges
            if 100 < x < 1800:
                score += 0.1
        
        return min(1.0, score)
    
    def _compute_focus_score(self, element: PerceptionElement) -> float:
        """Score based on focus history.
        
        Args:
            element: Candidate element
            
        Returns:
            Focus history score 0.0-1.0
        """
        if not element.text:
            return 0.0
        
        # Check if element was recently focused
        if element.text in self._focus_history[-5:]:
            return 1.0
        elif element.text in self._focus_history:
            return 0.5
        
        # Currently focused element
        if element.focused:
            return 0.8
        
        return 0.0
    
    def record_focus(self, element_text: str) -> None:
        """Record an element as having been focused.
        
        Args:
            element_text: Text of focused element
        """
        if element_text:
            self._focus_history.append(element_text)
            # Keep history bounded
            if len(self._focus_history) > 20:
                self._focus_history = self._focus_history[-20:]
    
    def clear_history(self) -> None:
        """Clear focus history."""
        self._focus_history.clear()


# Global resolver instance
_resolver_instance: Optional[ElementResolver] = None


def get_element_resolver() -> ElementResolver:
    """Get global element resolver instance.
    
    Returns:
        Singleton ElementResolver
    """
    global _resolver_instance
    if _resolver_instance is None:
        _resolver_instance = ElementResolver()
    return _resolver_instance
