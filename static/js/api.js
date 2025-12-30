/**
 * API Client wrapper for Fetch API
 * Handles error parsing, loading states, and common headers
 */

export class ApiClient {
    constructor(options = {}) {
        this.baseUrl = options.baseUrl || '';
        this.defaultHeaders = {
            'Accept': 'application/json',
            ...options.headers
        };
    }

    async request(endpoint, options = {}) {
        const url = `${this.baseUrl}${endpoint}`;
        const headers = { ...this.defaultHeaders, ...options.headers };
        
        // Handle body for JSON
        let body = options.body;
        if (body && typeof body === 'object' && !(body instanceof FormData)) {
            // Only set JSON Content-Type when we actually send JSON
            headers['Content-Type'] = 'application/json';
            body = JSON.stringify(body);
        } else if (body instanceof FormData) {
            // Let the browser set multipart boundary
            delete headers['Content-Type'];
        } else if (!body) {
            // Avoid sending Content-Type on GET/DELETE without a body
            delete headers['Content-Type'];
        }

        const config = {
            ...options,
            headers,
            body
        };

        // Show loading if requested
        if (options.showLoading) {
            document.getElementById('loading-overlay').classList.remove('d-none');
        }

        try {
            const response = await fetch(url, config);
            
            // Handle 401 Unauthorized (redirect to login)
            if (response.status === 401) {
                const data = await response.json().catch(() => ({}));
                if (data.login_required) {
                    window.location.href = '/login?next=' + encodeURIComponent(window.location.pathname);
                    return;
                }
            }

            const data = await response.json().catch(() => ({}));

            if (!response.ok) {
                throw {
                    status: response.status,
                    message: data.error || data.message || 'An error occurred',
                    data
                };
            }

            return data;
        } catch (error) {
            console.error('API Error:', error);
            throw error;
        } finally {
            if (options.showLoading) {
                document.getElementById('loading-overlay').classList.add('d-none');
            }
        }
    }

    get(endpoint, options = {}) {
        return this.request(endpoint, { ...options, method: 'GET' });
    }

    post(endpoint, body, options = {}) {
        return this.request(endpoint, { ...options, method: 'POST', body });
    }

    put(endpoint, body, options = {}) {
        return this.request(endpoint, { ...options, method: 'PUT', body });
    }

    patch(endpoint, body, options = {}) {
        return this.request(endpoint, { ...options, method: 'PATCH', body });
    }

    delete(endpoint, options = {}) {
        return this.request(endpoint, { ...options, method: 'DELETE' });
    }
}

export const api = new ApiClient();
