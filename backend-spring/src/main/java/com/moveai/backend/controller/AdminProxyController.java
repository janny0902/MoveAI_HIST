package com.moveai.backend.controller;

import jakarta.servlet.http.HttpServletRequest;
import java.net.URI;
import java.util.Enumeration;
import java.util.List;
import java.util.Set;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestTemplate;

/**
 * 관리자 Vue UI → Cloud Run(matching/vision) BFF.
 * 브라우저는 동일 출처 /api/admin/* 만 호출해 CORS를 피한다.
 */
@RestController
@RequestMapping("/api/admin")
public class AdminProxyController {

    private static final Set<String> SKIP_REQ_HEADERS = Set.of(
            "host", "connection", "content-length", "transfer-encoding",
            "accept-encoding", "origin", "referer", "cookie"
    );

    private final RestTemplate adminProxyRestTemplate;

    @Value("${admin.matching.base-url:https://matching-processor-xi6ooeq3ta-du.a.run.app}")
    private String matchingBaseUrl;

    @Value("${admin.vision.base-url:https://vision-processor-xi6ooeq3ta-du.a.run.app}")
    private String visionBaseUrl;

    public AdminProxyController(@Qualifier("adminProxyRestTemplate") RestTemplate adminProxyRestTemplate) {
        this.adminProxyRestTemplate = adminProxyRestTemplate;
    }

    @RequestMapping(value = "/matching/**", method = {
            RequestMethod.GET, RequestMethod.POST, RequestMethod.PUT,
            RequestMethod.PATCH, RequestMethod.DELETE
    })
    public ResponseEntity<byte[]> proxyMatching(
            HttpServletRequest request,
            @RequestBody(required = false) byte[] body
    ) {
        return proxy(request, body, matchingBaseUrl, "/api/admin/matching");
    }

    @RequestMapping(value = "/vision/**", method = {
            RequestMethod.GET, RequestMethod.POST, RequestMethod.PUT,
            RequestMethod.PATCH, RequestMethod.DELETE
    })
    public ResponseEntity<byte[]> proxyVision(
            HttpServletRequest request,
            @RequestBody(required = false) byte[] body
    ) {
        return proxy(request, body, visionBaseUrl, "/api/admin/vision");
    }

    private ResponseEntity<byte[]> proxy(
            HttpServletRequest request,
            byte[] body,
            String baseUrl,
            String pathPrefix
    ) {
        String uri = request.getRequestURI();
        String suffix = uri.length() > pathPrefix.length()
                ? uri.substring(pathPrefix.length())
                : "";
        if (suffix.isEmpty()) {
            suffix = "/";
        } else if (!suffix.startsWith("/")) {
            suffix = "/" + suffix;
        }

        String query = request.getQueryString();
        String target = baseUrl.replaceAll("/$", "") + suffix;
        if (query != null && !query.isBlank()) {
            target = target + "?" + query;
        }

        HttpMethod method = HttpMethod.valueOf(request.getMethod());
        HttpHeaders headers = copyRequestHeaders(request);
        byte[] payload = body != null ? body : new byte[0];
        HttpEntity<byte[]> entity = new HttpEntity<>(payload, headers);

        ResponseEntity<byte[]> upstream = adminProxyRestTemplate.exchange(
                URI.create(target),
                method,
                entity,
                byte[].class
        );

        HttpHeaders respHeaders = new HttpHeaders();
        List<String> contentTypes = upstream.getHeaders().get(HttpHeaders.CONTENT_TYPE);
        if (contentTypes != null && !contentTypes.isEmpty()) {
            respHeaders.set(HttpHeaders.CONTENT_TYPE, contentTypes.get(0));
        } else {
            respHeaders.setContentType(MediaType.APPLICATION_JSON);
        }
        return new ResponseEntity<>(upstream.getBody(), respHeaders, upstream.getStatusCode());
    }

    private HttpHeaders copyRequestHeaders(HttpServletRequest request) {
        HttpHeaders headers = new HttpHeaders();
        Enumeration<String> names = request.getHeaderNames();
        if (names == null) {
            return headers;
        }
        while (names.hasMoreElements()) {
            String name = names.nextElement();
            if (SKIP_REQ_HEADERS.contains(name.toLowerCase())) {
                continue;
            }
            Enumeration<String> values = request.getHeaders(name);
            while (values.hasMoreElements()) {
                headers.add(name, values.nextElement());
            }
        }
        return headers;
    }
}
