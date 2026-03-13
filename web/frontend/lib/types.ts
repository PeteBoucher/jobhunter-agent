export interface Skill {
  id: number;
  skill_name: string;
  proficiency: number | null;
  category: string | null;
}

export interface Preferences {
  target_titles: string[] | null;
  target_industries: string[] | null;
  preferred_locations: string[] | null;
  preferred_countries?: string[];
  salary_min: number | null;
  salary_max: number | null;
  experience_level: string | null;
  remote_preference: string | null;
  contract_types: string[] | null;
}

export interface User {
  id: number;
  google_id: string | null;
  email: string | null;
  name: string | null;
  location: string | null;
  title: string | null;
  created_at: string | null;
  skills: Skill[];
  preferences: Preferences | null;
}

export interface MatchScore {
  match_score: number | null;
  skill_score: number | null;
  title_score: number | null;
  experience_score: number | null;
  location_or_remote_score: number | null;
  salary_score: number | null;
}

export interface Job {
  id: number;
  source: string | null;
  title: string | null;
  company: string | null;
  department: string | null;
  location: string | null;
  remote: string | null;
  salary_min: number | null;
  salary_max: number | null;
  description: string | null;
  requirements: string[] | null;
  nice_to_haves: string[] | null;
  apply_url: string | null;
  posted_date: string | null;
  scraped_at: string | null;
  company_industry: string | null;
  match: MatchScore | null;
}

export interface Application {
  id: number;
  job_id: number;
  user_id: number | null;
  status: string | null;
  application_date: string | null;
  notes: string | null;
  created_at: string | null;
  updated_at: string | null;
  job_title: string | null;
  job_company: string | null;
}

export type ApplicationStatus =
  | "saved"
  | "applied"
  | "interview_scheduled"
  | "interviewed"
  | "offer"
  | "rejected"
  | "withdrawn";
