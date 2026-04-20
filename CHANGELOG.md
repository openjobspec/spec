# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0](https://github.com/openjobspec/spec/compare/v0.3.0...v0.4.0) (2026-04-20)


### Features

* add graceful shutdown signal handler ([b7b9b70](https://github.com/openjobspec/spec/commit/b7b9b704cc67dbd75bd7bd2670eaad812bba3777))
* add initial project structure ([f717e3d](https://github.com/openjobspec/spec/commit/f717e3dd419b72685d2ba93b84fca46ed47f59a8))
* add initial project structure ([9c99810](https://github.com/openjobspec/spec/commit/9c99810c368acf04fa991e6d62b5dfeeeef754ff))
* add retry backoff configuration ([65fe033](https://github.com/openjobspec/spec/commit/65fe033081b27e63e0a0742363a7a1e508ddc3f8))
* add retry backoff configuration ([5773466](https://github.com/openjobspec/spec/commit/5773466d542e3c86acf215b31225f55eb504dcfe))
* add RFC-0012 draft for priority queue extension ([a7a78aa](https://github.com/openjobspec/spec/commit/a7a78aaee9f9a31e76a8892e16d14c3bf8b9cc03))
* add workflow chain primitive ([379bac2](https://github.com/openjobspec/spec/commit/379bac2b271987104e54af149c29623857253161))
* expose batch enqueue endpoint ([bda67af](https://github.com/openjobspec/spec/commit/bda67af7940a5d7294e102bf3e908695e0397cd5))
* expose batch enqueue endpoint ([561e196](https://github.com/openjobspec/spec/commit/561e196438841110d756312da593ad74eb4c8422))
* implement core handler interfaces ([eb3e854](https://github.com/openjobspec/spec/commit/eb3e8540abcfedd6a7129b026795fbf39b099bb9))
* implement core handler interfaces ([7673b50](https://github.com/openjobspec/spec/commit/7673b50fbedbe751509eed71ec2f7997be8e971d))
* update OpenAPI specification with latest endpoint definitions ([7be9835](https://github.com/openjobspec/spec/commit/7be983552a3f8ec439c9900b9f6dbaf1941e0c58))


### Bug Fixes

* correct job state transition guard ([e1323d3](https://github.com/openjobspec/spec/commit/e1323d3270d26c0fa364f6b36a6e188599a8c112))
* correct job state transition guard ([8409e2d](https://github.com/openjobspec/spec/commit/8409e2d7c42491bedc009ff51681d582f6c2bac8))
* correct timestamp serialization ([7e1c3f4](https://github.com/openjobspec/spec/commit/7e1c3f4bac691482b88ef578cb9a29271e141e5d))
* correct timestamp serialization ([152fff9](https://github.com/openjobspec/spec/commit/152fff93fdae9a4d71487d1ca170f3dbfbb68201))
* handle nil pointer in middleware chain ([272fa3a](https://github.com/openjobspec/spec/commit/272fa3a033531b6d492984fffc8d4a6f32a54d31))
* handle nil pointer in middleware chain ([ba6eb0d](https://github.com/openjobspec/spec/commit/ba6eb0d0ef0afe723abbeb24731bf66209c330a4))
* prevent double-close on worker pool ([06bc006](https://github.com/openjobspec/spec/commit/06bc0063e21d1f89225506f8764ebfd2188d8914))
* resolve edge case in input validation ([2d29cf0](https://github.com/openjobspec/spec/commit/2d29cf082b68e6cf112c61ed7df062f4ee481e9a))
* resolve edge case in input validation ([a504669](https://github.com/openjobspec/spec/commit/a5046698584002ffee173582bc0bc82c67a94be5))


### Performance Improvements

* cache compiled regex patterns ([dde98e2](https://github.com/openjobspec/spec/commit/dde98e2ecfd11be045df7fa9b8fa3e95011401be))
* optimize data processing loop ([ecc4a67](https://github.com/openjobspec/spec/commit/ecc4a67378ba3b624d33d6b12dbbc91a791e466b))
* optimize data processing loop ([9a2aee1](https://github.com/openjobspec/spec/commit/9a2aee106f308b5809e1012ab111de7da9a23a41))
* reduce allocations in hot path ([1d6a9b2](https://github.com/openjobspec/spec/commit/1d6a9b230324c4dc791f28b885d1a3bd35f33e59))
* reduce allocations in hot path ([1ad9c1c](https://github.com/openjobspec/spec/commit/1ad9c1c0f256bebe2bcc4b40198ef5607c277725))

## [Unreleased]

## [0.4.0] - 2026-04-20

### Added
- Initial release
