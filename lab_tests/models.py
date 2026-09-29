"""
Lab test management models for DiagnoseIt
"""
from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal


class LabTestType(models.Model):
    """Model for different types of lab tests"""
    
    # Basic information
    name = models.CharField(max_length=200, unique=True)
    display_name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=100, blank=True)  # e.g., "Hematology", "Chemistry", "Endocrinology"
    
    # Aliases for better matching during PDF parsing
    aliases = models.JSONField(default=list, blank=True)  # Alternative names for the test
    
    # Default unit and reference ranges
    default_unit = models.CharField(max_length=50)
    normal_min = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    normal_max = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    
    # Status indicators
    is_active = models.BooleanField(default=True)

    # Where the entry came from, and whether someone changed it in the app. populate_lab_tests runs on every
    # deploy and would otherwise undo an edit, so it skips an entry marked edited_by_user.
    SOURCE_CATALOG = 'catalog'
    SOURCE_USER = 'user'
    source = models.CharField(
        max_length=10,
        choices=[(SOURCE_CATALOG, 'Built in'), (SOURCE_USER, 'Added in the app')],
        default=SOURCE_CATALOG,
    )
    edited_by_user = models.BooleanField(
        default=False,
        help_text="Someone changed this entry in the app, so populate_lab_tests leaves it alone",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['category', 'display_name']
        verbose_name = "Lab Test Type"
        verbose_name_plural = "Lab Test Types"
    
    def __str__(self):
        return f"{self.display_name} ({self.category})"


class LabTestUnit(models.Model):
    """Model for different units of measurement for lab tests"""
    
    # Basic information
    name = models.CharField(max_length=50, unique=True)
    display_name = models.CharField(max_length=100)
    symbol = models.CharField(max_length=20, blank=True)
    category = models.CharField(max_length=50)  # e.g., "concentration", "count", "ratio"
    
    # Conversion information
    is_base_unit = models.BooleanField(default=False)
    conversion_factor = models.DecimalField(
        max_digits=15, 
        decimal_places=8, 
        default=Decimal('1.0'),
        help_text="Factor to convert to base unit"
    )
    
    # Status
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['category', 'name']
        verbose_name = "Lab Test Unit"
        verbose_name_plural = "Lab Test Units"
    
    def __str__(self):
        return f"{self.display_name} ({self.symbol})"


class LabTestTypeUnit(models.Model):
    """Many-to-many relationship between test types and their supported units"""
    
    test_type = models.ForeignKey(LabTestType, on_delete=models.CASCADE, related_name='supported_units')
    unit = models.ForeignKey(LabTestUnit, on_delete=models.CASCADE, related_name='test_types')
    
    # Reference ranges for this specific unit
    normal_min = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    normal_max = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    
    # Conversion factor from default unit to this unit
    conversion_factor = models.DecimalField(
        max_digits=15, 
        decimal_places=8, 
        default=Decimal('1.0')
    )
    
    # Status
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['test_type', 'unit']
        verbose_name = "Test Type Unit"
        verbose_name_plural = "Test Type Units"
    
    def __str__(self):
        return f"{self.test_type.display_name} - {self.unit.display_name}"


class UnitConversion(models.Model):
    """Model for unit conversions between different units"""

    test_type = models.ForeignKey(
        LabTestType,
        on_delete=models.CASCADE,
        related_name='unit_conversions',
        help_text="Analyte this conversion factor applies to",
    )
    
    from_unit = models.ForeignKey(
        LabTestUnit, 
        on_delete=models.CASCADE, 
        related_name='conversions_from'
    )
    to_unit = models.ForeignKey(
        LabTestUnit, 
        on_delete=models.CASCADE, 
        related_name='conversions_to'
    )
    
    # Conversion factor: to_value = from_value * conversion_factor
    conversion_factor = models.DecimalField(
        max_digits=15, 
        decimal_places=8,
        help_text="Factor to convert from_unit to to_unit"
    )
    
    # Reverse conversion factor for efficiency
    reverse_factor = models.DecimalField(
        max_digits=15, 
        decimal_places=8,
        help_text="Factor to convert to_unit back to from_unit"
    )
    
    # Additional information
    formula = models.CharField(max_length=200, blank=True, help_text="Human-readable conversion formula")
    notes = models.TextField(blank=True)
    
    # Status
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['test_type', 'from_unit', 'to_unit'],
                name='unique_test_type_unit_conversion',
            )
        ]
        verbose_name = "Unit Conversion"
        verbose_name_plural = "Unit Conversions"
    
    def __str__(self):
        return f"{self.test_type.name}: {self.from_unit.name} → {self.to_unit.name}"
    
    def convert_value(self, value):
        """Convert a value from from_unit to to_unit"""
        return Decimal(str(value)) * self.conversion_factor
    
    def reverse_convert_value(self, value):
        """Convert a value from to_unit back to from_unit"""
        return Decimal(str(value)) * self.reverse_factor


class LabTestPattern(models.Model):
    """Model for regex patterns used in PDF parsing"""
    
    test_type = models.ForeignKey(LabTestType, on_delete=models.CASCADE, related_name='patterns')
    
    # Pattern information
    pattern_name = models.CharField(max_length=100)
    regex_pattern = models.TextField(help_text="Regex pattern for matching this test in PDF text")
    priority = models.IntegerField(default=1, help_text="Higher priority patterns are tried first")
    
    # Extraction information
    value_group = models.IntegerField(default=1, help_text="Regex group number containing the value")
    unit_group = models.IntegerField(null=True, blank=True, help_text="Regex group number containing the unit")
    range_group = models.IntegerField(null=True, blank=True, help_text="Regex group number containing the reference range")
    
    # Status
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['test_type', '-priority', 'pattern_name']
        verbose_name = "Lab Test Pattern"
        verbose_name_plural = "Lab Test Patterns"
    
    def __str__(self):
        return f"{self.test_type.display_name} - {self.pattern_name}"


class LabTestValidationRule(models.Model):
    """Model for validation rules for lab test values"""
    
    test_type = models.ForeignKey(LabTestType, on_delete=models.CASCADE, related_name='validation_rules')
    unit = models.ForeignKey(LabTestUnit, on_delete=models.CASCADE, related_name='validation_rules')
    
    # Validation criteria
    min_value = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    max_value = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    
    # Reference ranges
    normal_min = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    normal_max = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    
    # Status indicators
    critical_low_min = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    critical_high_max = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    
    # Additional information
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['test_type', 'unit']
        verbose_name = "Lab Test Validation Rule"
        verbose_name_plural = "Lab Test Validation Rules"
    
    def __str__(self):
        return f"{self.test_type.display_name} - {self.unit.display_name}"
    
    def validate_value(self, value):
        """Validate a test value and return status"""
        try:
            val = float(value)
            
            # Check if value is within acceptable range
            if self.min_value is not None and val < float(self.min_value):
                return "INVALID", "Value below minimum acceptable range"
            if self.max_value is not None and val > float(self.max_value):
                return "INVALID", "Value above maximum acceptable range"
            
            # Check critical values
            if self.critical_low_min is not None and val < float(self.critical_low_min):
                return "CRITICAL_LOW", "Critical low value"
            if self.critical_high_max is not None and val > float(self.critical_high_max):
                return "CRITICAL_HIGH", "Critical high value"
            
            # Check normal range
            if self.normal_min is not None and self.normal_max is not None:
                if val < float(self.normal_min):
                    return "LOW", "Below normal range"
                elif val > float(self.normal_max):
                    return "HIGH", "Above normal range"
                else:
                    return "NORMAL", "Within normal range"
            
            return "UNKNOWN", "No reference range available"
            
        except (ValueError, TypeError):
            return "INVALID", "Invalid numeric value"


class UserTestAlias(models.Model):
    """A printed test name one user linked to a catalog test; it applies to that user's results only."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='test_aliases')
    name = models.CharField(max_length=200, help_text="The printed name as the user linked it")
    match_key = models.CharField(max_length=400, help_text="lab_tests.matching.alias_key of the name")
    test_type = models.ForeignKey(LabTestType, on_delete=models.CASCADE, related_name='user_aliases')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = "User Test Alias"
        verbose_name_plural = "User Test Aliases"
        constraints = [
            models.UniqueConstraint(fields=['user', 'match_key'], name='unique_user_test_alias'),
        ]

    def __str__(self):
        return f"{self.name} -> {self.test_type.display_name}"
