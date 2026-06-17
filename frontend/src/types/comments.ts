export interface CommentAuthor {
  id: number;
  username: string;
  profile: {
    nickname: string | null;
    avatar: string | null;
    avatar_url: string | null;
    bio: string | null;
  };
}

export interface Comment {
  id: number;
  content: string;
  created_at: string;
  updated_at: string;
  parent_id: number | null;
  author: CommentAuthor;
  replies: Comment[];
}
