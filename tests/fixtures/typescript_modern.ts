import { Injectable, Component } from "@angular/core";

export module LegacyMod {
    export function legacyHelper(): number {
        return 42;
    }
}

export enum Color {
    Red = "red",
    Green = "green",
    Blue = "blue",
}

export interface Serializer<T> {
    serialize(value: T): string;
    deserialize(raw: string): T;
}

export type Maybe<T> = T | null | undefined;

export function identity<T>(value: T): T {
    return value;
}

export function pickBy<T extends Record<string, unknown>, K extends keyof T>(
    obj: T,
    keys: readonly K[],
): Pick<T, K> {
    const result = {} as Pick<T, K>;
    for (const k of keys) {
        result[k] = obj[k];
    }
    return result;
}

@Injectable({ providedIn: "root" })
export class UserService<T = string> {
    private cache: Map<string, T> = new Map();
    get(key: string): T | undefined {
        return this.cache.get(key);
    }
}

@Component({
    selector: "app-root",
    template: "<div></div>",
})
export class AppComponent {
    title = "demo";
}

const tuple = [1, 2, 3] as const;

interface Point { x: number; y: number; }
const p = { x: 1, y: 2 } satisfies Point;
