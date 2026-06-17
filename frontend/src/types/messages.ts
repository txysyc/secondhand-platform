export interface MessageParticipantProfile {
  nickname: string | null;
  avatar: string | null;
  avatar_url: string | null;
  bio: string | null;
}

export interface MessageParticipant {
  id: number;
  username: string;
  profile: MessageParticipantProfile;
}

export interface Conversation {
  id: number;
  participant_a: MessageParticipant;
  participant_b: MessageParticipant;
  other_participant: MessageParticipant;
  unread_count: number;
  latest_message_content: string | null;
  latest_message_created_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: number;
  conversation_id: number;
  sender: MessageParticipant;
  content: string;
  read_at: string | null;
  created_at: string;
}
