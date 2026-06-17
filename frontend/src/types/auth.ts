export interface Profile {
  nickname: string;
  avatar: string | null;
  avatar_url: string | null;
  bio: string;
}

export interface User {
  id: number;
  username: string;
  email: string;
  profile?: Profile;
}

export interface TokenResponse {
  access: string;
  refresh: string;
}
