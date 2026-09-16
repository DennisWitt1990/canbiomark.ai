import type { HttpClient } from "./HttpClient";

/** Role names as the backend spells them. */
export const UserRole = {
    Administrator: "administrator",
    Researcher: "researcher",
} as const;

export type UserRoleName = (typeof UserRole)[keyof typeof UserRole];

/** Raw shape of an account as it comes over the wire. */
export interface CurrentUserPayload {
    user_id: string;
    username: string;
    display_name: string;
    role: UserRoleName;
    is_administrator: boolean;
    quota_bytes: number;
    quota_gigabytes: number;
    must_change_password: boolean;
    created_at: string;
    last_login_at: string | null;
}

/**
 * The signed-in account.
 *
 * A class rather than a bare interface, so that the rules about what a user may
 * see live next to the data instead of being repeated in every component.
 */
export class CurrentUser {
    readonly userId: string;
    readonly username: string;
    readonly displayName: string;
    readonly role: UserRoleName;
    readonly quotaBytes: number;
    readonly quotaGigabytes: number;
    readonly mustChangePassword: boolean;
    readonly lastLoginAt: Date | null;

    constructor(payload: CurrentUserPayload) {
        this.userId = payload.user_id;
        this.username = payload.username;
        this.displayName = payload.display_name || payload.username;
        this.role = payload.role;
        this.quotaBytes = payload.quota_bytes;
        this.quotaGigabytes = payload.quota_gigabytes;
        this.mustChangePassword = payload.must_change_password;
        this.lastLoginAt = payload.last_login_at ? new Date(payload.last_login_at) : null;
    }

    get isAdministrator(): boolean {
        return this.role === UserRole.Administrator;
    }

    /** Initials shown in the header avatar. */
    get initials(): string {
        return this.displayName
            .split(/\s+/)
            .filter(Boolean)
            .slice(0, 2)
            .map((part) => part[0]!.toUpperCase())
            .join("");
    }
}

export interface PasswordPolicy {
    minimum_length: number;
    description: string;
}

/** Sign in, sign out and password self service. */
export class AuthenticationApi {
    constructor(private readonly httpClient: HttpClient) {}

    async logIn(username: string, password: string): Promise<CurrentUser> {
        const payload = await this.httpClient.post<CurrentUserPayload>("/auth/login", {
            username,
            password,
        });
        return new CurrentUser(payload);
    }

    async logOut(): Promise<void> {
        await this.httpClient.post<{ ok: boolean }>("/auth/logout");
    }

    async fetchCurrentUser(): Promise<CurrentUser> {
        const payload = await this.httpClient.get<CurrentUserPayload>("/auth/me");
        return new CurrentUser(payload);
    }

    async changeOwnPassword(currentPassword: string, newPassword: string): Promise<string> {
        const response = await this.httpClient.post<{ message: string }>(
            "/auth/change-password",
            { current_password: currentPassword, new_password: newPassword },
        );
        return response.message;
    }

    async fetchPasswordPolicy(): Promise<PasswordPolicy> {
        return this.httpClient.get<PasswordPolicy>("/auth/password-policy");
    }
}
