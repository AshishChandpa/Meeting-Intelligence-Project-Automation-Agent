"""Transcript preprocessing module for improved requirement extraction.

This module provides strategies for handling long transcripts by:
1. Structuring raw transcript text into analyzable chunks
2. Extracting speaker-specific information
3. Identifying topic transitions
4. Creating context-aware segments for better LLM processing
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class TranscriptSegment:
    """A single segment of a transcript with metadata."""
    speaker: str
    timestamp: str
    content: str
    segment_id: int
    topic_keywords: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)


@dataclass
class TopicSection:
    """A section of transcript focused on a specific topic."""
    title: str
    start_time: str
    end_time: str
    segments: List[TranscriptSegment]
    summary: str = ""
    key_points: List[str] = field(default_factory=list)


class TranscriptPreprocessor:
    """Preprocesses transcripts for improved requirement extraction."""

    def __init__(self):
        self.topic_keywords = {
            'overview': ['overview', 'background', 'introduction', 'context'],
            'requirements': ['need', 'want', 'requirement', 'feature', 'functionality', 'should', 'could'],
            'technical': ['api', 'integration', 'platform', 'tech', 'backend', 'frontend', 'data'],
            'timeline': ['timeline', 'deadline', 'when', 'asap', 'launch', 'deliverable'],
            'budget': ['budget', 'cost', 'price', 'quote', 'proposal'],
            'competition': ['competitor', 'competition', 'similar', 'existing', 'market'],
            'modules': ['module', 'section', 'part', 'component', 'feature'],
        }

    def parse_transcript(self, raw_transcript: str) -> List[TranscriptSegment]:
        """Parse raw transcript into structured segments.

        Args:
            raw_transcript: Raw transcript text with timestamp format:
                          "0:11 - Speaker Name\\nContent here..."

        Returns:
            List of TranscriptSegment objects
        """
        segments = []

        # Split by timestamp pattern (e.g., "0:11 - ", "14:08 - ")
        lines = raw_transcript.split('\n')
        current_speaker = None
        current_timestamp = None
        current_content = []

        for line in lines:
            line = line.strip()

            # Match timestamp pattern: "数字:数字 - "
            timestamp_match = re.match(r'^(\d+:\d+)\s*-\s*(.+?)$', line)

            if timestamp_match:
                # Save previous segment if exists
                if current_speaker and current_content:
                    content = ' '.join(current_content).strip()
                    if content:
                        segments.append(TranscriptSegment(
                            speaker=current_speaker,
                            timestamp=current_timestamp,
                            content=content,
                            segment_id=len(segments),
                            topic_keywords=self._extract_topic_keywords(content)
                        ))

                # Start new segment
                current_timestamp = timestamp_match.group(1)
                speaker_line = timestamp_match.group(2).strip()
                current_speaker = speaker_line
                current_content = []

            elif current_speaker:
                # Continuation of current speaker's content
                if line:
                    current_content.append(line)

        # Don't forget the last segment
        if current_speaker and current_content:
            content = ' '.join(current_content).strip()
            if content:
                segments.append(TranscriptSegment(
                    speaker=current_speaker,
                    timestamp=current_timestamp,
                    content=content,
                    segment_id=len(segments),
                    topic_keywords=self._extract_topic_keywords(content)
                ))

        logger.info(f"Parsed {len(segments)} segments from transcript")
        return segments

    def _extract_topic_keywords(self, content: str) -> List[str]:
        """Extract topic keywords from content."""
        keywords = []
        content_lower = content.lower()

        for topic, topic_words in self.topic_keywords.items():
            if any(word in content_lower for word in topic_words):
                keywords.append(topic)

        return keywords

    def group_by_topic(self, segments: List[TranscriptSegment]) -> List[TopicSection]:
        """Group segments into topic-focused sections.

        Args:
            segments: List of transcript segments

        Returns:
            List of TopicSection objects
        """
        if not segments:
            return []

        sections = []
        current_section = None
        section_buffer = []
        min_section_size = 3  # Minimum segments per section

        for segment in segments:
            # Determine if this starts a new topic section
            if not current_section:
                # Start first section
                current_section = {
                    'topic': segment.topic_keywords[0] if segment.topic_keywords else 'general',
                    'segments': [segment]
                }
            elif segment.topic_keywords and segment.topic_keywords[0] != current_section['topic']:
                # Topic changed, finalize current section if large enough
                if len(current_section['segments']) >= min_section_size:
                    sections.append(self._create_topic_section(current_section['segments']))

                # Start new section
                current_section = {
                    'topic': segment.topic_keywords[0],
                    'segments': [segment]
                }
            else:
                # Same topic, add to current section
                current_section['segments'].append(segment)

        # Don't forget the last section
        if current_section and len(current_section['segments']) >= min_section_size:
            sections.append(self._create_topic_section(current_section['segments']))

        logger.info(f"Grouped into {len(sections)} topic sections")
        return sections

    def _create_topic_section(self, segments: List[TranscriptSegment]) -> TopicSection:
        """Create a TopicSection from a list of segments."""
        # Determine topic from most common keywords
        all_keywords = []
        for seg in segments:
            all_keywords.extend(seg.topic_keywords)

        topic = max(set(all_keywords), key=all_keywords.count) if all_keywords else 'general'

        return TopicSection(
            title=f"{topic.title()} Discussion",
            start_time=segments[0].timestamp,
            end_time=segments[-1].timestamp,
            segments=segments
        )

    def create_chunked_prompts(
        self,
        segments: List[TranscriptSegment],
        chunk_size: int = 10,
        overlap: int = 2
    ) -> List[str]:
        """Create overlapping text chunks for LLM processing.

        Args:
            segments: List of transcript segments
            chunk_size: Number of segments per chunk
            overlap: Number of overlapping segments between chunks

        Returns:
            List of formatted text chunks
        """
        chunks = []

        for i in range(0, len(segments), chunk_size - overlap):
            chunk_segments = segments[i:i + chunk_size]

            # Format chunk as readable text
            chunk_text = self._format_segments(chunk_segments)
            chunks.append(chunk_text)

            if i + chunk_size >= len(segments):
                break

        logger.info(f"Created {len(chunks)} chunks (size={chunk_size}, overlap={overlap})")
        return chunks

    def _format_segments(self, segments: List[TranscriptSegment]) -> str:
        """Format segments as readable text with timestamps."""
        lines = []

        for seg in segments:
            lines.append(f"[{seg.timestamp}] {seg.speaker}:")
            lines.append(seg.content)
            lines.append("")  # Empty line for readability

        return '\n'.join(lines)

    def extract_speaker_summary(self, segments: List[TranscriptSegment]) -> Dict[str, Dict]:
        """Extract summary statistics by speaker.

        Returns:
            Dict mapping speaker_name -> {word_count, segment_count, topics}
        """
        speaker_stats = {}

        for seg in segments:
            if seg.speaker not in speaker_stats:
                speaker_stats[seg.speaker] = {
                    'segment_count': 0,
                    'word_count': 0,
                    'topics': set()
                }

            speaker_stats[seg.speaker]['segment_count'] += 1
            speaker_stats[seg.speaker]['word_count'] += len(seg.content.split())
            speaker_stats[seg.speaker]['topics'].update(seg.topic_keywords)

        # Convert sets to lists for JSON serialization
        for speaker in speaker_stats:
            speaker_stats[speaker]['topics'] = list(speaker_stats[speaker]['topics'])

        return speaker_stats

    def identify_client_requirements(self, segments: List[TranscriptSegment]) -> List[str]:
        """Identify explicit requirement statements from client.

        Looks for patterns like:
        - "I want..."
        - "We need..."
        - "The app should..."
        - "It would be good if..."
        """
        requirements = []
        requirement_patterns = [
            r'(?:i want|i need|i would like|i\'d like|we want|we need)',
            r'(?:the app|the system|the platform|it) (?:should|could|needs to|must)',
            r'(?:there should be|there needs to be|we could add)',
            r'(?:can we|could we|would it be possible)',
            r'(?:there could be|another module|another section)',
            r'(?:users? can|you can|they can)',
        ]

        secondary_speakers = {
            'team member 1',
            'team member 2',
            'team member 3',
        }

        high_signal_terms = {
            'module', 'feature', 'integration', 'api', 'dashboard', 'geofence',
            'notification', 'comparison', 'marketplace', 'onboarding', 'sprint',
            'property', 'loan', 'cashflow', 'budget', 'story', 'tour', 'legacy',
        }

        for seg in segments:
            speaker_lower = seg.speaker.lower()

            # Primary source: explicit client statements
            if 'client' in speaker_lower:
                for pattern in requirement_patterns:
                    matches = re.finditer(pattern, seg.content, re.IGNORECASE)
                    for match in matches:
                        # Extract the full sentence
                        start = max(0, match.start() - 50)
                        end = min(len(seg.content), match.end() + 150)
                        requirement = seg.content[start:end].strip()

                        # Clean up the requirement
                        requirement = re.sub(r'^\W+', '', requirement)
                        requirement = re.sub(r'\W+$', '', requirement)

                        if len(requirement) > 20:  # Filter out too-short matches
                            requirements.append(f"[{seg.timestamp}] {requirement}")

            # Secondary source: requirement paraphrases from discovery team
            elif speaker_lower in secondary_speakers:
                content_lower = seg.content.lower()
                if any(term in content_lower for term in high_signal_terms):
                    snippet = seg.content.strip()
                    if len(snippet) > 35:
                        requirements.append(f"[{seg.timestamp}] {snippet[:220].strip()}")

        return requirements

    def create_extraction_context(
        self,
        raw_transcript: str,
        strategy: str = 'topic'
    ) -> Dict:
        """Create optimized context for requirement extraction.

        Args:
            raw_transcript: Raw transcript text
            strategy: 'topic', 'chunked', or 'full'

        Returns:
            Dict with processed context ready for LLM
        """
        segments = self.parse_transcript(raw_transcript)

        if strategy == 'topic':
            sections = self.group_by_topic(segments)
            return {
                'strategy': 'topic-based',
                'sections': [
                    {
                        'title': section.title,
                        'time_range': f"{section.start_time} - {section.end_time}",
                        'content': self._format_segments(section.segments)
                    }
                    for section in sections
                ],
                'speaker_summary': self.extract_speaker_summary(segments),
                'client_requirements': self.identify_client_requirements(segments)
            }

        elif strategy == 'chunked':
            chunks = self.create_chunked_prompts(segments)
            return {
                'strategy': 'chunked',
                'chunks': chunks,
                'total_chunks': len(chunks),
                'speaker_summary': self.extract_speaker_summary(segments),
                'client_requirements': self.identify_client_requirements(segments)
            }

        else:  # full
            return {
                'strategy': 'full',
                'content': raw_transcript,
                'speaker_summary': self.extract_speaker_summary(segments),
                'client_requirements': self.identify_client_requirements(segments)
            }


# ── Convenience Functions ───────────────────────────────────────────────

def preprocess_transcript(raw_transcript: str, strategy: str = 'topic') -> Dict:
    """Convenience function to preprocess a transcript.

    Args:
        raw_transcript: Raw transcript text
        strategy: 'topic', 'chunked', or 'full'

    Returns:
        Processed context dict
    """
    preprocessor = TranscriptPreprocessor()
    return preprocessor.create_extraction_context(raw_transcript, strategy)


def extract_client_voice(raw_transcript: str) -> List[str]:
    """Extract only client statements for focused review.

    Args:
        raw_transcript: Raw transcript text

    Returns:
        List of client statements with timestamps
    """
    preprocessor = TranscriptPreprocessor()
    segments = preprocessor.parse_transcript(raw_transcript)

    client_statements = []
    for seg in segments:
        if 'client' in seg.speaker.lower():
            client_statements.append(f"[{seg.timestamp}] {seg.content}")

    return client_statements
