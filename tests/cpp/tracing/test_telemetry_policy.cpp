#include <gtest/gtest.h>

#include <chrono>
#include <cstdint>
#include <map>
#include <mutex>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

#include "scaler/tracing/environment.h"
#include "scaler/tracing/handover_queue.h"
#include "scaler/tracing/limits.h"
#include "scaler/tracing/sampler.h"

namespace {

// below and above the bound of a 0.5 ratio, which is 2^63
constexpr uint64_t lowTraceIDHalf  = 0x0000000000000001;
constexpr uint64_t highTraceIDHalf = 0xFFFFFFFFFFFFFFFF;

scaler::tracing::EnvironmentLookup environment(std::map<std::string, std::string> variables)
{
    return [variables = std::move(variables)](std::string_view name) -> std::optional<std::string> {
        auto found = variables.find(std::string {name});
        if (found == variables.end()) {
            return std::nullopt;
        }
        return found->second;
    };
}

scaler::tracing::Sampler sampler(std::map<std::string, std::string> variables, std::vector<std::string>& warnings)
{
    return scaler::tracing::Sampler::fromEnvironment(environment(std::move(variables)), warnings);
}

}  // namespace

TEST(SamplerTest, DefaultsToParentBasedAlwaysOn)
{
    std::vector<std::string> warnings {};
    const auto defaultSampler = sampler({}, warnings);

    EXPECT_TRUE(defaultSampler.shouldSample(std::nullopt, highTraceIDHalf));
    EXPECT_TRUE(defaultSampler.shouldSample(true, highTraceIDHalf));
    EXPECT_FALSE(defaultSampler.shouldSample(false, highTraceIDHalf));
    EXPECT_TRUE(warnings.empty());
}

TEST(SamplerTest, AlwaysOffDropsEvenChildrenOfSampledParents)
{
    std::vector<std::string> warnings {};
    const auto alwaysOff = sampler({{"OTEL_TRACES_SAMPLER", "always_off"}}, warnings);

    EXPECT_FALSE(alwaysOff.shouldSample(std::nullopt, lowTraceIDHalf));
    EXPECT_FALSE(alwaysOff.shouldSample(true, lowTraceIDHalf));
}

TEST(SamplerTest, ParentBasedAlwaysOffFollowsAParentAndDropsRoots)
{
    std::vector<std::string> warnings {};
    const auto parentBased = sampler({{"OTEL_TRACES_SAMPLER", "PARENTBASED_ALWAYS_OFF"}}, warnings);

    EXPECT_FALSE(parentBased.shouldSample(std::nullopt, lowTraceIDHalf));
    EXPECT_TRUE(parentBased.shouldSample(true, lowTraceIDHalf));
    EXPECT_TRUE(warnings.empty());
}

TEST(SamplerTest, TraceIDRatioComparesTheLowHalfAgainstTheBound)
{
    std::vector<std::string> warnings {};
    const auto half = sampler({{"OTEL_TRACES_SAMPLER", "traceidratio"}, {"OTEL_TRACES_SAMPLER_ARG", "0.5"}}, warnings);

    EXPECT_TRUE(half.shouldSample(std::nullopt, lowTraceIDHalf));
    EXPECT_FALSE(half.shouldSample(std::nullopt, highTraceIDHalf));
    EXPECT_FALSE(half.shouldSample(true, highTraceIDHalf));  // not parent based: the ratio decides
}

TEST(SamplerTest, TheRatioBoundsSampleNothingAndEverything)
{
    std::vector<std::string> warnings {};
    const auto none = sampler({{"OTEL_TRACES_SAMPLER", "traceidratio"}, {"OTEL_TRACES_SAMPLER_ARG", "0"}}, warnings);
    const auto all  = sampler({{"OTEL_TRACES_SAMPLER", "traceidratio"}, {"OTEL_TRACES_SAMPLER_ARG", "1"}}, warnings);

    EXPECT_FALSE(none.shouldSample(std::nullopt, lowTraceIDHalf));
    EXPECT_TRUE(all.shouldSample(std::nullopt, highTraceIDHalf));
}

TEST(SamplerTest, AnUnknownSamplerFallsBackToParentBasedAlwaysOnWithAWarning)
{
    std::vector<std::string> warnings {};
    const auto fallback = sampler({{"OTEL_TRACES_SAMPLER", "jaeger_remote"}}, warnings);

    EXPECT_TRUE(fallback.shouldSample(std::nullopt, highTraceIDHalf));
    EXPECT_FALSE(fallback.shouldSample(false, highTraceIDHalf));
    EXPECT_EQ(warnings.size(), 1U);
}

TEST(SamplerTest, AnInvalidRatioSamplesEverythingWithAWarning)
{
    std::vector<std::string> warnings {};
    const auto invalid =
        sampler({{"OTEL_TRACES_SAMPLER", "parentbased_traceidratio"}, {"OTEL_TRACES_SAMPLER_ARG", "1.5"}}, warnings);

    EXPECT_TRUE(invalid.shouldSample(std::nullopt, highTraceIDHalf));
    EXPECT_EQ(warnings.size(), 1U);
}

TEST(SpanLimitsTest, DefaultsTo128OfEachAndNoLength)
{
    std::vector<std::string> warnings {};
    const auto limits = scaler::tracing::SpanLimits::fromEnvironment(environment({}), warnings);

    EXPECT_EQ(limits._maxAttributes, 128U);
    EXPECT_EQ(limits._maxEvents, 128U);
    EXPECT_EQ(limits._maxLinks, 128U);
    EXPECT_EQ(limits._maxAttributeLength, std::nullopt);
    EXPECT_TRUE(warnings.empty());
}

TEST(SpanLimitsTest, TheGeneralLimitsAreTheDefaultsOfTheSpecificOnes)
{
    std::vector<std::string> warnings {};
    const auto limits = scaler::tracing::SpanLimits::fromEnvironment(
        environment(
            {{"OTEL_ATTRIBUTE_COUNT_LIMIT", "4"},
             {"OTEL_EVENT_ATTRIBUTE_COUNT_LIMIT", "2"},
             {"OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT", "8"},
             {"OTEL_SPAN_EVENT_COUNT_LIMIT", "unset"}}),
        warnings);

    EXPECT_EQ(limits._maxAttributes, 4U);
    EXPECT_EQ(limits._maxEventAttributes, 2U);
    EXPECT_EQ(limits._maxAttributeLength, 8U);
    EXPECT_EQ(limits._maxEvents, std::nullopt);
}

TEST(SpanLimitsTest, AnInvalidLimitKeepsItsDefaultWithAWarning)
{
    std::vector<std::string> warnings {};
    const auto limits =
        scaler::tracing::SpanLimits::fromEnvironment(environment({{"OTEL_SPAN_LINK_COUNT_LIMIT", "-1"}}), warnings);

    EXPECT_EQ(limits._maxLinks, 128U);
    EXPECT_EQ(warnings.size(), 1U);
}

TEST(LogLimitsTest, TheLogRecordLimitsDefaultToTheGeneralOnes)
{
    std::vector<std::string> warnings {};
    const auto limits = scaler::tracing::LogLimits::fromEnvironment(
        environment({{"OTEL_ATTRIBUTE_COUNT_LIMIT", "3"}, {"OTEL_LOGRECORD_ATTRIBUTE_VALUE_LENGTH_LIMIT", "2"}}),
        warnings);

    EXPECT_EQ(limits._maxAttributes, 3U);
    EXPECT_EQ(limits._maxAttributeLength, 2U);
}

TEST(HandoverQueueTest, ConsumesEveryPushedRecordOnItsThread)
{
    std::mutex mutex {};
    std::vector<int> consumed {};
    scaler::tracing::HandoverQueue<int> queue {16, [&](int& record) {
                                                   std::lock_guard lock {mutex};
                                                   consumed.push_back(record);
                                               }};
    for (int record_i = 0; record_i < 10; ++record_i) {
        EXPECT_TRUE(queue.push(int {record_i}));
    }

    EXPECT_TRUE(queue.waitUntilConsumed(std::chrono::steady_clock::now() + std::chrono::seconds {5}));
    std::lock_guard lock {mutex};
    EXPECT_EQ(consumed.size(), 10U);
}

TEST(HandoverQueueTest, DropsWhenFullAndAfterStop)
{
    std::mutex blocker {};
    std::unique_lock blocked {blocker};  // holds the consumer on its first record, so the queue fills
    scaler::tracing::HandoverQueue<int> queue {1, [&](int& /*record*/) { std::lock_guard wait {blocker}; }};

    EXPECT_TRUE(queue.push(1));  // taken by the consumer, which then waits
    while (!queue.push(2)) {     // the queue holds one more once the consumer took the first
    }
    EXPECT_FALSE(queue.push(3));

    blocked.unlock();
    queue.stop();
    EXPECT_FALSE(queue.push(4));
}
