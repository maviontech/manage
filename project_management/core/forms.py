# core/forms.py
from django import forms

STATUS_CHOICES = [
    ('Planned', 'Planned'), ('Active', 'Active'), ('Completed', 'Completed'), ('On Hold', 'On Hold')
]

class ProjectForm(forms.Form):
    name = forms.CharField(max_length=255, required=True, widget=forms.TextInput(attrs={"class":"form-control"}))
    description = forms.CharField(required=False, widget=forms.Textarea(attrs={"class":"form-control", "rows":4}))
    start_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type":"date","class":"form-control"}))
    end_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type":"date","class":"form-control"}))
    status = forms.ChoiceField(choices=STATUS_CHOICES, widget=forms.Select(attrs={"class":"form-control"}))

class SubprojectForm(forms.Form):
    name = forms.CharField(max_length=255, required=True, widget=forms.TextInput(attrs={"class":"form-control"}))
    description = forms.CharField(required=False, widget=forms.Textarea(attrs={"class":"form-control", "rows":3}))
