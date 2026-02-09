"""CV parsing module for extracting structured data from CV markdown."""

import re
from typing import Any, Dict, List, Optional


class CVParser:
    """Parse CV markdown and extract structured information."""

    def __init__(self, cv_text: str):
        """Initialize parser with CV text."""
        self.cv_text = cv_text
        self.lines = cv_text.split("\n")

    def parse(self) -> Dict:
        """Parse CV and return structured data."""
        return {
            "personal_info": self._parse_personal_info(),
            "professional_summary": self._parse_section("Professional Summary"),
            "skills": self._parse_skills(),
            "experience": self._parse_experience(),
            "education": self._parse_education(),
            "certifications": self._parse_section(
                "Certifications|Awards & Recognition"
            ),
            "projects": self._parse_section("Projects"),
            "languages": self._parse_languages(),
        }

    def _parse_personal_info(self) -> Dict:
        """Extract personal information from CV."""
        info = {
            "name": self._extract_name(),
            "email": self._extract_email(),
            "phone": self._extract_phone(),
            "location": self._extract_location(),
            "title": self._extract_title(),
        }
        return info

    def _extract_name(self) -> Optional[str]:
        """Extract full name (usually in first heading)."""
        for line in self.lines[:10]:
            if line.startswith("# "):
                return line.replace("# ", "").strip()
        return None

    def _extract_email(self) -> Optional[str]:
        """Extract email address."""
        match = re.search(
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", self.cv_text
        )
        return match.group(0) if match else None

    def _extract_phone(self) -> Optional[str]:
        """Extract phone number."""
        match = re.search(r"\+?[0-9\s\-\(\)]{10,}", self.cv_text)
        return match.group(0).strip() if match else None

    def _extract_location(self) -> Optional[str]:
        """Extract location from contact section."""
        # Look for "- **Location**:" pattern
        pattern = r"\*\*Location\*\*:\s*([^\n]+)"
        match = re.search(pattern, self.cv_text)
        if match:
            return match.group(1).strip()

        # Fallback: look for "location:" in first 500 chars
        for line in self.lines[:20]:
            if "location" in line.lower():
                match = re.search(r":\s*(.+?)$", line)
                if match:
                    return match.group(1).strip()
        return None

    def _extract_title(self) -> Optional[str]:
        """Extract job title/current role."""
        # Look for "- **Title**:" pattern
        pattern = r"\*\*Title\*\*:\s*([^\n]+)"
        match = re.search(pattern, self.cv_text)
        if match:
            return match.group(1).strip()

        # Fallback: look for "title:" in first 500 chars
        for line in self.lines[:20]:
            if "title" in line.lower():
                match = re.search(r":\s*(.+?)$", line)
                if match:
                    return match.group(1).strip()
        return None

    def _parse_section(self, section_name: str) -> Optional[str]:
        """Extract text content of a section."""
        pattern = rf"## {section_name}\n(.*?)(?=## |\Z)"
        match = re.search(pattern, self.cv_text, re.IGNORECASE | re.DOTALL)
        if match:
            content = match.group(1).strip()
            # Remove bullet points and clean up
            content = re.sub(r"^[-*]\s+", "", content, flags=re.MULTILINE)
            return content if content else None
        return None

    def _parse_skills(self) -> Dict[str, List[str]]:
        """Extract skills organized by category."""
        skills: Dict[str, List[str]] = {
            "technical": [],
            "soft": [],
            "languages": [],
        }

        # Find Core Skills or Skills section
        pattern = r"## .*?[Ss]kill.*?\n(.*?)(?=## |\Z)"
        match = re.search(pattern, self.cv_text, re.DOTALL)

        if not match:
            return skills

        skills_text = match.group(1)

        # Split by subsections (### Technical, ### Professional, etc.)
        subsections = re.split(r"\n###\s+", skills_text)

        for subsection in subsections:
            lines = subsection.split("\n")
            if not lines:
                continue

            # First line is the category name
            category_line = lines[0].lower()
            category = "technical" if "technical" in category_line else "soft"
            if "language" in category_line:
                category = "languages"

            # Extract bullet points from this subsection
            items = re.findall(r"[-*]\s+([^\n]+)", subsection)
            for item in items:
                item_clean = item.strip()
                if item_clean:
                    skills[category].append(item_clean)

        return skills

    def _parse_experience(self) -> List[Dict[str, Optional[str]]]:
        """Extract work experience entries."""
        experiences: List[Dict[str, Optional[str]]] = []

        # Find Professional Experience section header and content
        pattern = r"##\s+[^\n]*[Ee]xperience[^\n]*\n(.*?)(?=\n##\s|\Z)"
        match = re.search(pattern, self.cv_text, re.DOTALL)

        if not match:
            return experiences

        exp_text = match.group(1)

        # Split by "###" headers (job titles)
        job_blocks = re.split(r"\n### ", exp_text)

        for block in job_blocks:
            if not block.strip():
                continue

            lines = block.split("\n")
            header = lines[0].strip()

            exp_dict: Dict[str, Optional[str]] = {
                "title": None,
                "company": None,
                "location": None,
                "duration": None,
                "description": None,
            }

            # Parse header: "Company | Title" or "Company - Title"
            if "|" in header:
                parts = header.split("|")
                exp_dict["company"] = parts[0].strip()
                exp_dict["title"] = parts[1].strip() if len(parts) > 1 else None
            elif "-" in header:
                parts = header.split("-")
                exp_dict["company"] = parts[0].strip()
                exp_dict["title"] = parts[1].strip() if len(parts) > 1 else None
            else:
                exp_dict["company"] = header

            # Parse metadata
            for line in lines[1:]:
                if "Location" in line or "location" in line:
                    location = re.sub(r"\*\*Location\*\*:\s*", "", line)
                    exp_dict["location"] = location.strip() or exp_dict.get("location")
                elif "Duration" in line or "duration" in line:
                    duration = re.sub(r"\*\*Duration\*\*:\s*", "", line)
                    exp_dict["duration"] = duration.strip() or exp_dict.get("duration")

            if exp_dict["company"]:
                experiences.append(exp_dict)

        return experiences

    def _parse_education(self) -> List[Dict[str, Optional[str]]]:
        """Extract education entries."""
        education: List[Dict[str, Optional[str]]] = []

        # Find Education section header and content
        pattern = r"##\s+[^\n]*[Ee]ducation[^\n]*\n(.*?)(?=\n##\s|\Z)"
        match = re.search(pattern, self.cv_text, re.DOTALL)

        if not match:
            return education

        edu_text = match.group(1)

        # Split by "###" headers (schools)
        edu_blocks = re.split(r"\n### ", edu_text)

        for block in edu_blocks:
            if not block.strip():
                continue

            lines = block.split("\n")
            header = lines[0].strip()

            edu_dict: Dict[str, Optional[str]] = {
                "school": None,
                "degree": None,
                "field": None,
                "duration": None,
                "location": None,
            }

            edu_dict["school"] = header

            # Parse metadata
            for line in lines[1:]:
                if "Location" in line or "location" in line:
                    location = re.sub(r"\*\*Location\*\*:\s*", "", line)
                    edu_dict["location"] = location.strip() or edu_dict.get("location")
                elif "Duration" in line or "duration" in line:
                    duration = re.sub(r"\*\*Duration\*\*:\s*", "", line)
                    edu_dict["duration"] = duration.strip() or edu_dict.get("duration")
                elif "Degree" in line or "degree" in line:
                    degree = re.sub(r"\*\*Degree\*\*:\s*", "", line)
                    edu_dict["degree"] = degree.strip() or edu_dict.get("degree")

            if edu_dict["school"]:
                education.append(edu_dict)

        return education

    def _parse_languages(self) -> List[str]:
        """Extract languages spoken."""
        languages = []

        # Look for Languages section or extract from skills
        pattern = r"## .*?[Ll]anguages.*?\n(.*?)(?=## |\Z)"
        match = re.search(pattern, self.cv_text, re.DOTALL)

        if match:
            lang_text = match.group(1)
            items = re.findall(r"[-*]\s+([^\n]+)", lang_text)
            languages.extend([item.strip() for item in items])

        return languages


def parse_cv_file(file_path: str) -> Dict[str, Any]:
    """Parse CV from markdown file."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            cv_text = f.read()
        parser = CVParser(cv_text)
        return parser.parse()
    except FileNotFoundError:
        print(f"✗ CV file not found: {file_path}")
        return {}
    except Exception as e:
        print(f"✗ Error parsing CV: {e}")
        return {}
