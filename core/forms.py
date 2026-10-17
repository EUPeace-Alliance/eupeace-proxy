from django import forms
from .models import GuestInvitation

class GuestInvitationForm(forms.ModelForm):
    class Meta:
        model = GuestInvitation
        fields = ['guest_email', 'duration_days']
        
        widgets = {
            'guest_email': forms.EmailInput(attrs={
                'class': 'form-control form-control-lg', 
                'placeholder': 'es. mario.rossi@oxford.ac.uk'
            }),
            'duration_days': forms.Select(
                choices=[
                    (7, '1 Week (Quick Access)'),
                    (30, '1 Month (Short Project)'),
                    (180, '6 Months (Academic Semester)'),
                    (365, '1 Year (Long-term Collaboration)'),
                ], 
                attrs={'class': 'form-select form-select-lg'}
            )
        }
        labels = {
            'guest_email': "Guest Email Address",
            'duration_days': "Access Duration"
        }