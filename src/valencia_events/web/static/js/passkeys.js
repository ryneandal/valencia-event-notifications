/**
 * Passkey (WebAuthn) frontend logic.
 * Handles registration and authentication ceremonies.
 */

/* Util to convert base64url string to Uint8Array */
function bufferDecode(value) {
    return Uint8Array.from(atob(value.replace(/-/g, "+").replace(/_/g, "/")), c => c.charCodeAt(0));
}

/* Util to convert ArrayBuffer/Uint8Array to base64url string */
function bufferEncode(value) {
    return btoa(String.fromCharCode.apply(null, new Uint8Array(value)))
        .replace(/\+/g, "-")
        .replace(/\//g, "_")
        .replace(/=/g, "");
}

async function registerPasskey() {
    try {
        // 1. Get options from server
        const optionsRes = await fetch("/auth/webauthn/register/options", { method: "POST" });
        if (!optionsRes.ok) throw new Error("Failed to get registration options");
        const options = await optionsRes.json();

        // Decode challenge and user.id
        options.challenge = bufferDecode(options.challenge);
        options.user.id = bufferDecode(options.user.id);

        // Decode excludeCredentials ids if present
        if (options.excludeCredentials) {
            for (let cred of options.excludeCredentials) {
                cred.id = bufferDecode(cred.id);
            }
        }

        // 2. Create credential
        const credential = await navigator.credentials.create({ publicKey: options });

        // 3. Send to server for verification
        const credentialJSON = {
            id: credential.id,
            rawId: bufferEncode(credential.rawId),
            type: credential.type,
            response: {
                attestationObject: bufferEncode(credential.response.attestationObject),
                clientDataJSON: bufferEncode(credential.response.clientDataJSON),
            },
        };

        const verifyRes = await fetch("/auth/webauthn/register/verify", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(credentialJSON),
        });

        if (verifyRes.ok) {
            alert("Passkey registered successfully!");
            window.location.reload();
        } else {
            const err = await verifyRes.json();
            alert(`Registration failed: ${err.detail}`);
        }
    } catch (e) {
        console.error(e);
        alert("Error registering passkey: " + e.message);
    }
}

async function loginPasskey() {
    try {
        // 1. Get options
        const optionsRes = await fetch("/auth/webauthn/login/options", { method: "POST" });
        if (!optionsRes.ok) throw new Error("Failed to get login options");
        const options = await optionsRes.json();

        // Decode challenge
        options.challenge = bufferDecode(options.challenge);

        // Decode allowCredentials ids if present
        if (options.allowCredentials) {
            for (let cred of options.allowCredentials) {
                cred.id = bufferDecode(cred.id);
            }
        }

        // 2. Get assertion
        const credential = await navigator.credentials.get({ publicKey: options });

        // 3. Send to server
        const credentialJSON = {
            id: credential.id,
            rawId: bufferEncode(credential.rawId),
            type: credential.type,
            response: {
                authenticatorData: bufferEncode(credential.response.authenticatorData),
                clientDataJSON: bufferEncode(credential.response.clientDataJSON),
                signature: bufferEncode(credential.response.signature),
                userHandle: credential.response.userHandle ? bufferEncode(credential.response.userHandle) : null,
            },
        };

        const verifyRes = await fetch("/auth/webauthn/login/verify", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(credentialJSON),
        });

        const result = await verifyRes.json();
        if (verifyRes.ok && result.status === "ok") {
            window.location.href = result.redirect || "/dashboard";
        } else {
            alert(`Login failed: ${result.detail || "Unknown error"}`);
        }
    } catch (e) {
        console.error(e);
        alert("Error logging in with passkey: " + e.message);
    }
}
