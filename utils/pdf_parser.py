"""
PDF parsing utilities for extracting medical data from lab reports and prescriptions
"""
import logging
import re
import json
from typing import Dict, List, Any, Optional
import pdfplumber
import pypdf
from io import BytesIO

logger = logging.getLogger(__name__)


class MedicalPDFParser:
    """Parser for medical PDF documents"""
    
    def __init__(self):
        # Common medical test patterns
        self.test_patterns = {
            'blood_glucose': r'(?i)(glucose|sugar|fbs|rbs|hba1c)',
            'creatinine': r'(?i)(creatinine|creat)',
            'urea': r'(?i)(urea|bun)',
            'cholesterol': r'(?i)(cholesterol|hdl|ldl|triglycerides)',
            'hemoglobin': r'(?i)(hemoglobin|hb|hgb)',
            'wbc': r'(?i)(wbc|white blood cell|leukocyte)',
            'rbc': r'(?i)(rbc|red blood cell|erythrocyte)',
            'platelet': r'(?i)(platelet|plt)',
            'sodium': r'(?i)(sodium|na)',
            'potassium': r'(?i)(potassium|k)',
            'calcium': r'(?i)(calcium|ca)',
            'phosphorus': r'(?i)(phosphorus|phosphate|po4)',
            'alt': r'(?i)(alt|alanine aminotransferase|sgpt)',
            'ast': r'(?i)(ast|aspartate aminotransferase|sgot)',
            'alkaline_phosphatase': r'(?i)(alkaline phosphatase|alp)',
            'bilirubin': r'(?i)(bilirubin|total bilirubin|direct bilirubin)',
            'protein': r'(?i)(total protein|albumin|globulin)',
            'tsh': r'(?i)(tsh|thyroid stimulating hormone)',
            't3': r'(?i)(t3|triiodothyronine)',
            't4': r'(?i)(t4|thyroxine)',
            'vitamin_d': r'(?i)(vitamin d|25-oh vitamin d)',
            'vitamin_b12': r'(?i)(vitamin b12|b12|cobalamin)',
            'folate': r'(?i)(folate|folic acid)',
            'iron': r'(?i)(iron|ferritin|transferrin)',
        }
        
        # Value extraction patterns
        self.value_patterns = [
            r'(\d+\.?\d*)\s*([a-zA-Z/%]+)?',  # Number with optional unit
            r'(\d+\.?\d*)\s*-\s*(\d+\.?\d*)',  # Range
            r'(\d+\.?\d*)\s*to\s*(\d+\.?\d*)',  # Range with "to"
        ]
        
        # Reference range patterns
        self.reference_patterns = [
            r'ref[:\s]*([^,\n]+)',
            r'reference[:\s]*([^,\n]+)',
            r'normal[:\s]*([^,\n]+)',
            r'range[:\s]*([^,\n]+)',
        ]

    def extract_text_from_pdf(self, pdf_file) -> str:
        """Extract text from PDF file"""
        try:
            # Try pdfplumber first (better for complex layouts)
            with pdfplumber.open(pdf_file) as pdf:
                text = ""
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
                return text
        except Exception as e:
            logger.warning(f"pdfplumber failed: {e}")
            try:
                # Fallback to pypdf
                pdf_reader = pypdf.PdfReader(pdf_file)
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
                return text
            except Exception as e2:
                logger.error(f"pypdf also failed: {e2}")
                return ""

    def extract_test_results(self, text: str) -> List[Dict[str, Any]]:
        """Extract test results from text"""
        results = []
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Check if line contains any test pattern
            for test_name, pattern in self.test_patterns.items():
                if re.search(pattern, line):
                    result = self._parse_test_line(line, test_name)
                    if result:
                        results.append(result)
                    break
        
        return results

    def _parse_test_line(self, line: str, test_name: str) -> Optional[Dict[str, Any]]:
        """Parse a single line containing test results"""
        # Extract test value
        value_match = None
        for pattern in self.value_patterns:
            match = re.search(pattern, line)
            if match:
                value_match = match
                break
        
        if not value_match:
            return None
        
        # Extract reference range
        ref_range = self._extract_reference_range(line)
        
        # Determine status
        status = self._determine_status(value_match.group(1), ref_range)
        
        return {
            'test_name': test_name,
            'value': value_match.group(1),
            'unit': value_match.group(2) if len(value_match.groups()) > 1 and value_match.group(2) and value_match.group(2).strip() else '',
            'reference_range': ref_range if ref_range else '',
            'status': status,
            'raw_line': line
        }

    def _extract_reference_range(self, line: str) -> str:
        """Extract reference range from line"""
        for pattern in self.reference_patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return ""

    def _determine_status(self, value: str, ref_range: str) -> str:
        """Determine if value is normal, high, or low"""
        try:
            val = float(value)
            if not ref_range:
                return "UNKNOWN"
            
            # Simple range parsing (e.g., "3.5-5.0", "3.5 - 5.0")
            range_match = re.search(r'(\d+\.?\d*)\s*[-–]\s*(\d+\.?\d*)', ref_range)
            if range_match:
                min_val = float(range_match.group(1))
                max_val = float(range_match.group(2))
                
                if val < min_val:
                    return "LOW"
                elif val > max_val:
                    return "HIGH"
                else:
                    return "NORMAL"
            
            # Check for "less than" or "greater than" patterns
            if re.search(r'<\s*(\d+\.?\d*)', ref_range):
                max_val = float(re.search(r'<\s*(\d+\.?\d*)', ref_range).group(1))
                return "HIGH" if val >= max_val else "NORMAL"
            
            if re.search(r'>\s*(\d+\.?\d*)', ref_range):
                min_val = float(re.search(r'>\s*(\d+\.?\d*)', ref_range).group(1))
                return "LOW" if val <= min_val else "NORMAL"
            
            return "UNKNOWN"
        except (ValueError, AttributeError):
            return "UNKNOWN"

    def extract_prescription_data(self, text: str) -> Dict[str, Any]:
        """Extract prescription data from text"""
        medications = []
        lines = text.split('\n')
        
        # Common medication patterns
        med_patterns = [
            r'([A-Z][a-z]+(?: [A-Z][a-z]+)*)\s+(\d+\s*mg|\d+\s*ml|\d+\s*tablet|\d+\s*capsule)',
            r'([A-Z][a-z]+(?: [A-Z][a-z]+)*)\s+(\d+)\s*(mg|ml|tablet|capsule)',
        ]
        
        for line in lines:
            line = line.strip()
            for pattern in med_patterns:
                match = re.search(pattern, line)
                if match:
                    medication = {
                        'medication_name': match.group(1),
                        'dosage': match.group(2),
                        'raw_line': line
                    }
                    medications.append(medication)
                    break
        
        return {
            'medications': medications,
            'raw_text': text
        }

    def parse_medical_report(self, pdf_file) -> Dict[str, Any]:
        """Parse a medical report PDF"""
        text = self.extract_text_from_pdf(pdf_file)
        if not text:
            return {'error': 'Could not extract text from PDF'}
        
        test_results = self.extract_test_results(text)
        
        return {
            'text': text,
            'test_results': test_results,
            'parsed_successfully': len(test_results) > 0
        }

    def parse_prescription(self, pdf_file) -> Dict[str, Any]:
        """Parse a prescription PDF"""
        text = self.extract_text_from_pdf(pdf_file)
        if not text:
            return {'error': 'Could not extract text from PDF'}
        
        prescription_data = self.extract_prescription_data(text)
        
        return {
            'text': text,
            'medications': prescription_data['medications'],
            'parsed_successfully': len(prescription_data['medications']) > 0
        }


def parse_medical_pdf(pdf_file) -> Dict[str, Any]:
    """Convenience function to parse medical PDF"""
    parser = MedicalPDFParser()
    return parser.parse_medical_report(pdf_file)


def parse_prescription_pdf(pdf_file) -> Dict[str, Any]:
    """Convenience function to parse prescription PDF"""
    parser = MedicalPDFParser()
    return parser.parse_prescription(pdf_file)
