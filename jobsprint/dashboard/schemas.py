from typing import Optional

from pydantic import BaseModel, Field


class SessionStartRequest(BaseModel):
    email: str
    password: str
    portal: str = "naukri"
    jobs_target: Optional[int] = None
    role: Optional[str] = None
    location: Optional[str] = None
    experience: Optional[int] = None
    job_age: Optional[int] = None


class QuestionAnswerRequest(BaseModel):
    answer: str


class PreferencesUpdate(BaseModel):
    role: Optional[str] = None
    location: Optional[str] = None
    experience: Optional[int] = None
    job_age_days: Optional[int] = None
    jobs_target: Optional[int] = None
    question_timeout_minutes: Optional[int] = None
    auto_apply_external: Optional[bool] = None


class KBEntryUpdate(BaseModel):
    answer: Optional[str] = None
    canonical_question: Optional[str] = None


class ProfileUpdate(BaseModel):
    Salutation: Optional[str] = None
    Full_name: Optional[str] = Field(None, alias="Full name")
    First_name: Optional[str] = Field(None, alias="First name")
    Last_name: Optional[str] = Field(None, alias="Last name")
    Location: Optional[str] = None
    Total_experience: Optional[str] = Field(None, alias="Total experience")
    Current_CTC: Optional[str] = Field(None, alias="Current CTC")
    Expected_salary: Optional[str] = Field(None, alias="Expected salary")
    Salary: Optional[str] = None
    Mobile: Optional[str] = None
    Email: Optional[str] = None
    Notice_period: Optional[str] = Field(None, alias="Notice period")
    Date_of_birth: Optional[str] = Field(None, alias="Date of birth")
    Gender: Optional[str] = None
    Preferred_work_location: Optional[str] = Field(None, alias="Preferred work location")
    Relocate: Optional[str] = None
    Highest_qualification: Optional[str] = Field(None, alias="Highest qualification")
    Resume_path: Optional[str] = Field(None, alias="Resume path")
    Cover_letter: Optional[str] = Field(None, alias="Cover letter")
    Skills: Optional[dict] = None

    model_config = {"populate_by_name": True}
